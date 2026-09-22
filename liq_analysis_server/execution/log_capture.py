from __future__ import annotations
import re, threading
from collections import deque
from pathlib import Path
from typing import IO
from ..config import MAX_LOG_CHARS

SECRET=re.compile(r"(?i)(password|token|secret|authorization|api[_-]?key)(\s*[:=]\s*)([^\s,;]+)")
def mask(text:str)->str: return SECRET.sub(r"\1\2***",text)

class LogCapture:
    def __init__(self,stdout_path:Path,stderr_path:Path):
        self.paths={"stdout":stdout_path,"stderr":stderr_path}; self.buffers={"stdout":deque(),"stderr":deque()}; self.sizes={"stdout":0,"stderr":0}; self.lock=threading.RLock()
    def start(self,stdout:IO[str]|None,stderr:IO[str]|None):
        for name,stream in (("stdout",stdout),("stderr",stderr)):
            if stream: threading.Thread(target=self._read,args=(name,stream),daemon=True,name=f"liq-log-{name}").start()
    def _read(self,name,stream):
        path=self.paths[name]; path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("a",encoding="utf-8",errors="replace") as out:
            for line in iter(stream.readline,""):
                out.write(line); out.flush()
                with self.lock:
                    self.buffers[name].append(line); self.sizes[name]+=len(line)
                    while self.sizes[name]>MAX_LOG_CHARS and self.buffers[name]: self.sizes[name]-=len(self.buffers[name].popleft())
    def get(self,stream="both",tail_lines=200,since_offset=None,max_chars=50000):
        names=[stream] if stream in self.buffers else ["stdout","stderr"]; result={}
        for name in names:
            text="".join(self.buffers[name])
            start=max(0,int(since_offset or 0)); part=text[start:] if since_offset is not None else "".join(text.splitlines(True)[-int(tail_lines):])
            result[name]=mask(part[:max_chars]); result[f"{name}_next_offset"]=len(text); result[f"{name}_truncated"]=len(part)>max_chars
        return result

