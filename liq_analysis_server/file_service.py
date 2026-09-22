from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import EXCLUDED_NAMES
from .path_service import PathService


class FileConflictError(RuntimeError):
    """파일이 READ 이후 외부에서 변경되어 안전하게 덮어쓸 수 없다."""


class FileService:
    def __init__(self, paths: PathService) -> None:
        self.paths = paths
        self._lock = threading.RLock()

    @staticmethod
    def _sha256_bytes(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _modified_at(path: Path) -> str:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()

    def _item(self, path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {
            "exists": True,
            "name": path.name,
            "path": self.paths.relative(path),
            "type": "directory" if path.is_dir() else "file",
            "size_bytes": path.stat().st_size if path.is_file() else None,
            "modified_at": self._modified_at(path),
        }
        if path.is_file():
            result["sha256"] = self._sha256_bytes(path.read_bytes())
        return result

    @staticmethod
    def _is_hidden_from_actions(path: Path) -> bool:
        name = path.name
        lower = name.lower()
        return (
            name in EXCLUDED_NAMES
            or lower.endswith((".pyc", ".pyo"))
            or "_org_" in lower
        )

    def list_root(self) -> dict[str, Any]:
        roots = [
            {**self._item(root), "path": str(root), "absolute_path": str(root)}
            for root in self.paths.roots
        ]
        return {
            "exists": True,
            "name": "registered_roots",
            "path": ".",
            "type": "root_list",
            "entries": roots,
            "entry_count": len(roots),
            "children": roots,
        }

    def list_directory(self, value: str) -> dict[str, Any]:
        path = self.paths.resolve(value, must_exist=True)
        if not path.is_dir():
            raise NotADirectoryError(str(path))
        children = [
            self._item(child)
            for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            if not self._is_hidden_from_actions(child)
        ]
        return {**self._item(path), "entries": children, "entry_count": len(children), "children": children}

    def get_path_info(self, value: str) -> dict[str, Any]:
        path = self.paths.resolve(value)
        if not path.exists():
            return {
                "exists": False,
                "name": path.name,
                "path": self.paths.relative(path),
                "type": "missing",
                "size_bytes": None,
                "modified_at": "",
                "sha256": "",
            }
        return self._item(path)

    def read_file(self, value: str, max_chars: int = 1_000_000) -> dict[str, Any]:
        path = self.paths.resolve(value, must_exist=True)
        if not path.is_file():
            raise IsADirectoryError(str(path))
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig", errors="replace")
        content = text[:max_chars]
        truncated = len(content) < len(text)
        return {
            **self._item(path),
            "content": content,
            "text": content,
            "content_chars": len(content),
            "line_count": len(text.splitlines()),
            "complete": not truncated,
            "truncated": truncated,
            "encoding": "utf-8",
            "sha256": self._sha256_bytes(raw),
        }

    def read_file_chunk(
        self,
        value: str,
        start_line: int = 1,
        line_count: int = 200,
        max_chars: int = 60_000,
    ) -> dict[str, Any]:
        path = self.paths.resolve(value, must_exist=True)
        if not path.is_file():
            raise IsADirectoryError(str(path))
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig", errors="replace")
        lines = text.splitlines(keepends=True)
        total = len(lines)
        if start_line < 1:
            raise ValueError("start_line은 1 이상이어야 한다")
        if start_line > max(total, 1):
            raise ValueError(f"start_line이 전체 줄 수를 초과한다: {start_line} > {total}")
        requested = lines[start_line - 1 : start_line - 1 + line_count]
        selected: list[str] = []
        selected_chars = 0
        char_truncated = False
        for line in requested:
            if selected and selected_chars + len(line) > max_chars:
                char_truncated = True
                break
            if not selected and len(line) > max_chars:
                selected.append(line[:max_chars])
                selected_chars = max_chars
                char_truncated = True
                break
            selected.append(line)
            selected_chars += len(line)
        content = "".join(selected)
        returned = len(selected)
        end_line = start_line + returned - 1 if returned else start_line - 1
        has_more = char_truncated or end_line < total
        complete = start_line == 1 and not has_more
        return {
            **self._item(path),
            "content": content,
            "text": content,
            "content_chars": len(content),
            "start_line": start_line,
            "end_line": end_line,
            "line_count": returned,
            "returned_line_count": returned,
            "total_line_count": total,
            "complete": complete,
            "truncated": char_truncated,
            "has_more": has_more,
            "next_start_line": end_line + 1 if has_more and not char_truncated else None,
            "encoding": "utf-8",
            "sha256": self._sha256_bytes(raw),
        }

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _backup_path(self, path: Path) -> Path:
        stamp = datetime.now().strftime("%y%m%d%H%M")
        base = path.with_name(f"{path.stem}_org_{stamp}{path.suffix}")
        if not base.exists():
            return base
        index = 1
        while True:
            candidate = path.with_name(f"{path.stem}_org_{stamp}_{index:02d}{path.suffix}")
            if not candidate.exists():
                return candidate
            index += 1

    def create_file(self, value: str, content: str) -> dict[str, Any]:
        with self._lock:
            path = self.paths.resolve(value)
            if path.exists():
                raise FileExistsError(str(path))
            if not path.parent.exists():
                raise FileNotFoundError(f"상위 디렉토리가 없다: {path.parent}")
            self._atomic_write(path, content)
            return {**self._item(path), "content_chars": len(content), "backup_path": "", "created": True}

    def update_file(self, value: str, content: str, expected_sha256: str = "") -> dict[str, Any]:
        with self._lock:
            path = self.paths.resolve(value, must_exist=True)
            if not path.is_file():
                raise IsADirectoryError(str(path))
            current_sha = self._sha256_bytes(path.read_bytes())
            if expected_sha256 and current_sha.lower() != expected_sha256.lower():
                raise FileConflictError(
                    f"파일이 읽은 뒤 변경되었다: expected_sha256={expected_sha256}, actual_sha256={current_sha}"
                )
            backup = self._backup_path(path)
            shutil.copy2(path, backup)
            self._atomic_write(path, content)
            return {
                **self._item(path),
                "content_chars": len(content),
                "backup_path": self.paths.relative(backup),
            }

    def delete_file(self, value: str) -> dict[str, Any]:
        with self._lock:
            path = self.paths.resolve(value, must_exist=True)
            if not path.is_file():
                raise IsADirectoryError(str(path))
            path.unlink()
            return {"deleted": value, "path": value, "type": "file", "exists": False}

    def create_directory(self, value: str) -> dict[str, Any]:
        with self._lock:
            path = self.paths.resolve(value)
            path.mkdir(parents=False, exist_ok=False)
            return {**self._item(path), "created": True}

    def delete_directory(self, value: str) -> dict[str, Any]:
        with self._lock:
            path = self.paths.resolve(value, must_exist=True)
            if not path.is_dir():
                raise NotADirectoryError(str(path))
            shutil.rmtree(path)
            return {"deleted": value, "path": value, "type": "directory", "exists": False}

    def move(self, source: str, target: str) -> dict[str, Any]:
        with self._lock:
            source_path = self.paths.resolve(source, must_exist=True)
            target_path = self.paths.resolve(target)
            if target_path.exists():
                raise FileExistsError(str(target_path))
            if not target_path.parent.exists():
                raise FileNotFoundError(f"대상 상위 디렉토리가 없다: {target_path.parent}")
            shutil.move(str(source_path), str(target_path))
            return {
                **self._item(target_path),
                "source_path": source,
                "target_path": self.paths.relative(target_path),
                "source_exists": False,
                "target_exists": True,
                "moved": True,
            }

    move_file = move
    move_directory = move

    def rename_file(self, value: str, new_name: str) -> dict[str, Any]:
        if not new_name or Path(new_name).name != new_name:
            raise ValueError("new_name에는 경로가 아닌 새 이름만 전달해야 한다")
        result = self.move(value, str(Path(value).with_name(new_name)))
        result["renamed"] = True
        return result

    rename_directory = rename_file

    def restore_latest_file(self, value: str) -> dict[str, Any]:
        with self._lock:
            path = self.paths.resolve(value, must_exist=True)
            pattern = f"{path.stem}_org_*{path.suffix}"
            backups = sorted(path.parent.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
            if not backups:
                raise FileNotFoundError(f"원복할 org 백업이 없다: {value}")
            selected = backups[0]
            current_backup = self._backup_path(path)
            shutil.copy2(path, current_backup)
            restored = selected.read_text(encoding="utf-8-sig", errors="replace")
            self._atomic_write(path, restored)
            return {
                **self._item(path),
                "content_chars": len(restored),
                "backup_path": self.paths.relative(current_backup),
                "restored_from": self.paths.relative(selected),
                "restored": True,
            }
