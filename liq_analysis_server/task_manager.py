from __future__ import annotations

import json
import os
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import MAX_WORKERS, TASK_ROOT, TASK_STATUS_DIRS

MAX_PUBLIC_STRING_CHARS = 50_000

Progress = Callable[[int, str, Any | None], None]

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

class TaskManager:
    def __init__(self, root: Path = TASK_ROOT, max_workers: int = MAX_WORKERS) -> None:
        self.root = root
        self.max_workers = max_workers
        self._lock = threading.RLock()
        self._executor: ThreadPoolExecutor | None = None
        self._records: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[tuple[str, str, str], str] = {}
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[], None]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _notify_listeners(self) -> None:
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener()
            except Exception:
                continue

    def start(self) -> None:
        with self._lock:
            if self._executor is not None:
                return
            for folder in TASK_STATUS_DIRS.values():
                (self.root / folder).mkdir(parents=True, exist_ok=True)
            self._load_records()
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="liq-action-task")

    def stop(self) -> None:
        with self._lock:
            executor, self._executor = self._executor, None
        if executor:
            executor.shutdown(wait=True, cancel_futures=False)

    def submit(self, *, session_id: str, api_name: str, category_code: str, command_code: str,
               target: dict[str, Any], handler: Callable[[Progress], Any], request_id: str = "") -> dict[str, Any]:
        self.start()
        idem = (session_id, request_id, command_code)
        with self._lock:
            if request_id and idem in self._idempotency:
                record = self._records[self._idempotency[idem]]
                return {"task_id": record["task_id"], "status": record["status"], "reused": True}
            task_id = uuid.uuid4().hex
            safe_target = self._sanitize_target(target)
            record = {"task_id": task_id, "session_id": session_id, "request_id": request_id,
                      "api_name": api_name, "category_code": category_code, "command_code": command_code,
                      "target": safe_target, "status": "WAITING", "progress": 0, "current_step": "접수",
                      "received_at": utcnow(), "started_at": "", "completed_at": "", "result": None, "error": None}
            self._records[task_id] = record
            if request_id:
                self._idempotency[idem] = task_id
            self._persist(record)
            self._notify_listeners()
            assert self._executor is not None
            self._executor.submit(self._run, task_id, handler)
            return {"task_id": task_id, "status": "WAITING", "reused": False}

    def execute_inline(
        self,
        *,
        session_id: str,
        api_name: str,
        category_code: str,
        command_code: str,
        target: dict[str, Any],
        handler: Callable[[Progress], Any],
        request_id: str = "",
    ) -> dict[str, Any]:
        """짧은 FILE 작업을 호출 안에서 완료하면서 기존 작업 이력/UI를 유지한다."""
        self.start()
        idem = (session_id, request_id, command_code)
        with self._lock:
            if request_id and idem in self._idempotency:
                return self.get(self._idempotency[idem])
            task_id = uuid.uuid4().hex
            record = {
                "task_id": task_id,
                "session_id": session_id,
                "request_id": request_id,
                "api_name": api_name,
                "category_code": category_code,
                "command_code": command_code,
                "target": self._sanitize_target(target),
                "status": "RUNNING",
                "progress": 1,
                "current_step": "실행",
                "received_at": utcnow(),
                "started_at": utcnow(),
                "completed_at": "",
                "result": None,
                "error": None,
            }
            self._records[task_id] = record
            if request_id:
                self._idempotency[idem] = task_id
            self._persist(record)
        self._notify_listeners()

        def progress(percent: int, step: str, partial: Any | None = None) -> None:
            fields: dict[str, Any] = {
                "progress": max(0, min(100, int(percent))),
                "current_step": step,
            }
            if partial is not None:
                fields["partial_result"] = partial
            self._update(task_id, **fields)

        try:
            result = handler(progress)
        except Exception as exc:
            self._update(
                task_id,
                status="FAILED",
                progress=100,
                current_step="실패",
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
                completed_at=utcnow(),
            )
            raise
        self._update(
            task_id,
            status="COMPLETED",
            progress=100,
            current_step="완료",
            result=result,
            completed_at=utcnow(),
        )
        return self.get(task_id)

    def _run(self, task_id: str, handler: Callable[[Progress], Any]) -> None:
        self._update(task_id, status="RUNNING", progress=1, current_step="실행", started_at=utcnow())
        def progress(percent: int, step: str, partial: Any | None = None) -> None:
            fields: dict[str, Any] = {"progress": max(0, min(100, int(percent))), "current_step": step}
            if partial is not None:
                fields["partial_result"] = partial
            self._update(task_id, **fields)
        try:
            result = handler(progress)
            self._update(task_id, status="COMPLETED", progress=100, current_step="완료", result=result, completed_at=utcnow())
        except Exception as exc:
            result = getattr(exc, "result", None)
            self._update(task_id, status="FAILED", progress=100, current_step="실패", result=result,
                         error={"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}, completed_at=utcnow())

    def get(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            if task_id not in self._records:
                raise FileNotFoundError(f"작업을 찾을 수 없다: {task_id}")
            return self._public_value(dict(self._records[task_id]))

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted((self._public_value(dict(v)) for v in self._records.values()), key=lambda x: x["received_at"], reverse=True)

    @classmethod
    def _sanitize_target(cls, target: dict[str, Any]) -> dict[str, Any]:
        result = dict(target)
        content = result.pop("content", None)
        if isinstance(content, str) and content:
            if content != "<omitted>":
                result["content_chars"] = len(content)
            result["content"] = "<omitted>"
        sql = result.pop("sql", None)
        if isinstance(sql, str) and sql:
            if sql != "<omitted>":
                result["sql_chars"] = len(sql)
            result["sql"] = "<omitted>"
        environment = result.get("environment")
        if isinstance(environment, dict) and environment:
            result["environment_keys"] = sorted(str(key) for key in environment)
            result["environment"] = "<omitted>"
        return result

    @classmethod
    def _public_value(cls, value: Any) -> Any:
        if isinstance(value, str):
            if len(value) <= MAX_PUBLIC_STRING_CHARS:
                return value
            return value[:MAX_PUBLIC_STRING_CHARS] + f"\n...[truncated {len(value) - MAX_PUBLIC_STRING_CHARS} chars]"
        if isinstance(value, dict):
            result = {str(key): cls._public_value(item) for key, item in value.items()}
            target = result.get("target")
            if isinstance(target, dict):
                result["target"] = cls._sanitize_target(target)
            return result
        if isinstance(value, list):
            return [cls._public_value(item) for item in value]
        if isinstance(value, tuple):
            return [cls._public_value(item) for item in value]
        return value

    def delete_by_status(self, statuses: set[str]) -> int:
        """사용자가 관리 UI에서 완료/실패 기록을 직접 정리한다."""
        normalized = {value.upper() for value in statuses}
        with self._lock:
            task_ids = [
                task_id
                for task_id, record in self._records.items()
                if record.get("status") in normalized
            ]
            for task_id in task_ids:
                record = self._records.pop(task_id)
                self._path(task_id, record["status"]).unlink(missing_ok=True)
                for key, value in list(self._idempotency.items()):
                    if value == task_id:
                        self._idempotency.pop(key, None)
            count = len(task_ids)
        if count:
            self._notify_listeners()
        return count

    def _update(self, task_id: str, **fields: Any) -> None:
        with self._lock:
            record = self._records[task_id]
            old = record["status"]
            record.update(fields)
            if record["status"] != old:
                old_path = self._path(task_id, old)
                if old_path.exists(): old_path.unlink()
            self._persist(record)
        self._notify_listeners()

    def _path(self, task_id: str, status: str) -> Path:
        return self.root / TASK_STATUS_DIRS[status] / f"{task_id}.json"

    def _persist(self, record: dict[str, Any]) -> None:
        path = self._path(record["task_id"], record["status"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        os.replace(temp, path)

    def _load_records(self) -> None:
        for status, folder in TASK_STATUS_DIRS.items():
            for path in (self.root / folder).glob("*.json"):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                    if status in {"WAITING", "RUNNING"}:
                        record.update(status="FAILED", error={"type": "Interrupted", "message": "서버 재시작으로 중단됨"}, completed_at=utcnow())
                        path.unlink(missing_ok=True); self._persist(record)
                    self._records[record["task_id"]] = record
                except Exception:
                    continue
