from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from ..config import PYTHON_EXECUTABLE
from ..path_service import PathService

class CommandBuilder:
    def __init__(self, paths: PathService): self.paths=paths
    def build(self, path: str, runner: str, arguments: list[str], python_executable: str="") -> tuple[list[str],str]:
        target=self.paths.resolve(path,must_exist=True); kind=(runner or self._kind(target)).lower()
        if kind=="python":
            exe=self._python(python_executable); return [exe,str(target),*map(str,arguments)],exe
        if kind in {"batch","cmd"}:
            if target.suffix.lower() not in {".bat",".cmd"}: raise ValueError("batch runner는 .bat/.cmd만 허용한다")
            return [os.environ.get("COMSPEC",r"C:\Windows\System32\cmd.exe"),"/d","/c",str(target),*map(str,arguments)],""
        if kind in {"executable","script"}:
            if target.suffix.lower() not in {".exe",".com"}: raise ValueError("직접 실행은 .exe/.com만 허용한다")
            return [str(target),*map(str,arguments)],""
        raise ValueError(f"지원하지 않는 runner다: {kind}")
    def _python(self,value):
        p=Path(value or PYTHON_EXECUTABLE).resolve()
        allowed = p==Path(PYTHON_EXECUTABLE).resolve() or self.paths.is_allowed(p)
        if not allowed or not p.exists(): raise ValueError(f"허용되지 않은 Python 실행 파일이다: {p}")
        return str(p)
    @staticmethod
    def _kind(path): return "python" if path.suffix.lower() in {".py",".pyw"} else "batch" if path.suffix.lower() in {".bat",".cmd"} else "executable"
