from __future__ import annotations

import configparser
import os
import re
import threading
from pathlib import Path
from typing import Any


ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class DbConnectionConfig:
    """DB 연결 목록을 별도 cfg에 저장하고 실행 중 즉시 반영한다."""

    def __init__(self, cfg_path: Path, default_connection: dict[str, Any]) -> None:
        self.cfg_path = cfg_path.resolve()
        self.default_connection = dict(default_connection)
        self._lock = threading.RLock()
        self._items: list[dict[str, Any]] = []
        self._default_id = ""
        self.reload()

    @property
    def items(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(dict(item) for item in self._items)

    def public_items(self) -> list[dict[str, Any]]:
        return [
            {key: value for key, value in item.items() if key != "password"}
            for item in self.items
        ]

    @property
    def default_id(self) -> str:
        with self._lock:
            return self._default_id

    def reload(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            self._items, configured_default = self._read()
            if not self._items:
                self._items = [{"id": "default", **self.default_connection}]
            ids = {str(item["id"]).lower(): str(item["id"]) for item in self._items}
            self._default_id = ids.get(configured_default.lower(), str(self._items[0]["id"]))
            if not self.cfg_path.exists() or configured_default != self._default_id:
                self._save()
            return self.items

    def get(self, connection_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if not self._items:
                raise ValueError("등록된 DB 연결이 없다")
            if not connection_id:
                return dict(self._items[0])
            wanted = connection_id.strip().lower()
            for item in self._items:
                if str(item["id"]).lower() == wanted:
                    return dict(item)
        raise ValueError(f"등록되지 않은 DB 연결이다: {connection_id}")

    def get_default(self) -> dict[str, Any]:
        return self.get(self.default_id)

    def set_default(self, connection_id: str) -> dict[str, Any]:
        with self._lock:
            selected = self.get(connection_id)
            self._default_id = str(selected["id"])
            self._save()
            return selected

    def add(self, item: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize(item)
        with self._lock:
            if any(existing["id"].lower() == normalized["id"].lower() for existing in self._items):
                raise ValueError(f"이미 등록된 DB ID이다: {normalized['id']}")
            self._items.append(normalized)
            self._save()
        return dict(normalized)

    def update(self, old_id: str, item: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize(item)
        with self._lock:
            index = next((i for i, value in enumerate(self._items) if value["id"].lower() == old_id.lower()), -1)
            if index < 0:
                raise ValueError(f"등록되지 않은 DB 연결이다: {old_id}")
            if any(i != index and value["id"].lower() == normalized["id"].lower() for i, value in enumerate(self._items)):
                raise ValueError(f"이미 등록된 DB ID이다: {normalized['id']}")
            self._items[index] = normalized
            if self._default_id.lower() == old_id.lower():
                self._default_id = normalized["id"]
            self._save()
        return dict(normalized)

    def remove(self, connection_id: str) -> dict[str, Any]:
        with self._lock:
            if len(self._items) == 1:
                raise ValueError("마지막 DB 연결은 삭제할 수 없다")
            index = next((i for i, value in enumerate(self._items) if value["id"].lower() == connection_id.lower()), -1)
            if index < 0:
                raise ValueError(f"등록되지 않은 DB 연결이다: {connection_id}")
            removed = self._items.pop(index)
            if self._default_id.lower() == connection_id.lower():
                self._default_id = str(self._items[0]["id"])
            self._save()
            return dict(removed)

    def _read(self) -> tuple[list[dict[str, Any]], str]:
        if not self.cfg_path.exists():
            return [], ""
        parser = configparser.ConfigParser()
        parser.read(self.cfg_path, encoding="utf-8")
        configured_default = parser.get("settings", "default", fallback="").strip()
        items: list[dict[str, Any]] = []
        for section in parser.sections():
            if not section.lower().startswith("database:"):
                continue
            connection_id = section.split(":", 1)[1].strip()
            values = parser[section]
            try:
                item = self._normalize({"id": connection_id, **dict(values)})
            except (ValueError, TypeError):
                continue
            items.append(item)
        return items, configured_default

    def _save(self) -> None:
        parser = configparser.ConfigParser()
        parser["settings"] = {"default": self._default_id or str(self._items[0]["id"])}
        for item in self._items:
            parser[f"database:{item['id']}"] = {
                "host": str(item["host"]),
                "port": str(item["port"]),
                "dbname": str(item["dbname"]),
                "user": str(item["user"]),
                "password": str(item["password"]),
                "sslmode": str(item.get("sslmode", "prefer")),
            }
        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cfg_path.with_suffix(self.cfg_path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            parser.write(handle)
        os.replace(temporary, self.cfg_path)

    @staticmethod
    def _normalize(item: dict[str, Any]) -> dict[str, Any]:
        connection_id = str(item.get("id", "")).strip()
        if not ID_RE.fullmatch(connection_id):
            raise ValueError("DB ID는 영문, 숫자, 밑줄, 하이픈만 사용할 수 있다")
        host = str(item.get("host", "")).strip()
        dbname = str(item.get("dbname") or item.get("database") or "").strip()
        user = str(item.get("user", "")).strip()
        if not host or not dbname or not user:
            raise ValueError("host, dbname, user 값이 필요하다")
        port = int(item.get("port", 5432))
        if not 1 <= port <= 65535:
            raise ValueError("DB port 범위가 올바르지 않다")
        return {
            "id": connection_id,
            "host": host,
            "port": port,
            "dbname": dbname,
            "user": user,
            "password": str(item.get("password", "")),
            "sslmode": str(item.get("sslmode", "prefer") or "prefer").strip(),
        }
