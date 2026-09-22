from __future__ import annotations

import configparser
import os
import threading
from pathlib import Path


class RootConfig:
    """등록된 작업 루트를 cfg 파일에 저장하고 즉시 반영한다."""

    SECTION = "roots"

    def __init__(self, cfg_path: Path, default_root: Path) -> None:
        self.cfg_path = cfg_path.resolve()
        self.default_root = default_root.expanduser().resolve()
        self._lock = threading.RLock()
        self._roots: list[Path] = []
        self.reload()

    @property
    def roots(self) -> tuple[Path, ...]:
        with self._lock:
            return tuple(self._roots)

    def reload(self) -> tuple[Path, ...]:
        with self._lock:
            roots = self._read()
            self._roots = roots or [self.default_root]
            if not self.cfg_path.exists() or not roots:
                self._save()
            return tuple(self._roots)

    def add(self, value: str | Path) -> Path:
        path = self._normalize_existing_directory(value)
        with self._lock:
            if path in self._roots:
                raise ValueError(f"이미 등록된 작업 루트이다: {path}")
            self._roots.append(path)
            self._save()
        return path

    def update(self, old_value: str | Path, new_value: str | Path) -> Path:
        old_path = Path(old_value).expanduser().resolve()
        new_path = self._normalize_existing_directory(new_value)
        with self._lock:
            try:
                index = self._roots.index(old_path)
            except ValueError as exc:
                raise ValueError(f"등록되지 않은 작업 루트이다: {old_path}") from exc
            if new_path != old_path and new_path in self._roots:
                raise ValueError(f"이미 등록된 작업 루트이다: {new_path}")
            self._roots[index] = new_path
            self._save()
        return new_path

    def remove(self, value: str | Path) -> Path:
        path = Path(value).expanduser().resolve()
        with self._lock:
            if path not in self._roots:
                raise ValueError(f"등록되지 않은 작업 루트이다: {path}")
            if len(self._roots) == 1:
                raise ValueError("마지막 작업 루트는 삭제할 수 없다")
            self._roots.remove(path)
            self._save()
        return path

    def _read(self) -> list[Path]:
        if not self.cfg_path.exists():
            return []
        parser = configparser.ConfigParser()
        parser.read(self.cfg_path, encoding="utf-8")
        values = parser[self.SECTION] if parser.has_section(self.SECTION) else {}
        roots: list[Path] = []
        for key in sorted(values, key=self._sort_key):
            raw = str(values[key]).strip()
            if not raw:
                continue
            path = Path(raw).expanduser().resolve()
            if path.is_dir() and path not in roots:
                roots.append(path)
        return roots

    def _save(self) -> None:
        parser = configparser.ConfigParser()
        parser[self.SECTION] = {
            f"root_{index:03d}": str(path)
            for index, path in enumerate(self._roots, start=1)
        }
        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.cfg_path.with_suffix(self.cfg_path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8", newline="") as handle:
            parser.write(handle)
        os.replace(temp, self.cfg_path)

    @staticmethod
    def _normalize_existing_directory(value: str | Path) -> Path:
        path = Path(value).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(str(path))
        if not path.is_dir():
            raise NotADirectoryError(str(path))
        return path

    @staticmethod
    def _sort_key(value: str) -> tuple[int, str]:
        try:
            return int(value.rsplit("_", 1)[-1]), value
        except ValueError:
            return 10**9, value
