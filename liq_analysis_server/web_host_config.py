from __future__ import annotations

import configparser
import os
import threading
from pathlib import Path
from urllib.parse import urlparse


class WebHostConfig:
    """URL 허용 호스트를 cfg 파일에 저장하고 실행 중 즉시 반영한다."""

    SECTION = "hosts"

    def __init__(self, cfg_path: Path, defaults) -> None:
        self.cfg_path = cfg_path.resolve()
        self.defaults = tuple(
            dict.fromkeys(str(value).strip().lower() for value in defaults if str(value).strip())
        )
        self._lock = threading.RLock()
        self._hosts: list[str] = []
        self.reload()

    @property
    def hosts(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._hosts)

    def reload(self) -> tuple[str, ...]:
        with self._lock:
            hosts = self._read()
            self._hosts = hosts or list(self.defaults)
            if not self.cfg_path.exists() or not hosts:
                self._save()
            return tuple(self._hosts)

    def add(self, value: str) -> str:
        host = self.normalize(value)
        with self._lock:
            if host in self._hosts:
                raise ValueError(f"이미 등록된 허용 호스트입니다: {host}")
            self._hosts.append(host)
            self._save()
        return host

    def update(self, old_value: str, new_value: str) -> str:
        old_host = self.normalize(old_value)
        new_host = self.normalize(new_value)
        with self._lock:
            if old_host not in self._hosts:
                raise ValueError(f"등록되지 않은 허용 호스트입니다: {old_host}")
            if new_host != old_host and new_host in self._hosts:
                raise ValueError(f"이미 등록된 허용 호스트입니다: {new_host}")
            self._hosts[self._hosts.index(old_host)] = new_host
            self._save()
        return new_host

    def remove(self, value: str) -> str:
        host = self.normalize(value)
        with self._lock:
            if host not in self._hosts:
                raise ValueError(f"등록되지 않은 허용 호스트입니다: {host}")
            if len(self._hosts) == 1:
                raise ValueError("마지막 허용 호스트는 삭제할 수 없습니다")
            self._hosts.remove(host)
            self._save()
        return host

    @staticmethod
    def normalize(value: str) -> str:
        raw = str(value).strip()
        if not raw:
            raise ValueError("호스트명 또는 URL을 입력하십시오")
        parsed = urlparse(raw if "://" in raw else f"//{raw}")
        host = (parsed.hostname or "").strip().lower().rstrip(".")
        if not host or any(character.isspace() for character in host):
            raise ValueError(f"올바르지 않은 호스트명 또는 URL입니다: {value}")
        return host

    def _read(self) -> list[str]:
        if not self.cfg_path.exists():
            return []
        parser = configparser.ConfigParser()
        parser.read(self.cfg_path, encoding="utf-8")
        values = parser[self.SECTION] if parser.has_section(self.SECTION) else {}
        hosts: list[str] = []
        for key in sorted(values, key=self._sort_key):
            raw = str(values[key]).strip()
            if raw:
                host = self.normalize(raw)
                if host not in hosts:
                    hosts.append(host)
        return hosts

    def _save(self) -> None:
        parser = configparser.ConfigParser()
        parser[self.SECTION] = {
            f"host_{index:03d}": host
            for index, host in enumerate(self._hosts, start=1)
        }
        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.cfg_path.with_suffix(self.cfg_path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8", newline="") as handle:
            parser.write(handle)
        os.replace(temp, self.cfg_path)

    @staticmethod
    def _sort_key(value: str) -> tuple[int, str]:
        try:
            return int(value.rsplit("_", 1)[-1]), value
        except ValueError:
            return 10**9, value
