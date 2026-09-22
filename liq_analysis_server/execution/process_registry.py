from __future__ import annotations
import json, os, threading
from pathlib import Path
from typing import Any
from ..config import PROCESS_ROOT

class ProcessRegistry:
    def __init__(self,root:Path=PROCESS_ROOT): self.root=root; self.lock=threading.RLock(); self.records={}
    def start(self):
        self.root.mkdir(parents=True,exist_ok=True)
        for p in self.root.glob("*.json"):
            try: self.records[p.stem]=json.loads(p.read_text(encoding="utf-8"))
            except Exception: continue
    def save(self,record):
        with self.lock:
            self.records[record["process_id"]]=record; p=self.root/f'{record["process_id"]}.json'; t=p.with_suffix('.tmp'); t.write_text(json.dumps(record,ensure_ascii=False,indent=2,default=str),encoding='utf-8'); os.replace(t,p)
    def get(self,pid):
        with self.lock:
            if pid not in self.records: raise FileNotFoundError(f"관리 프로세스를 찾을 수 없다: {pid}")
            return dict(self.records[pid])
    def list(self):
        with self.lock: return [dict(x) for x in self.records.values()]
    def delete(self,process_ids):
        with self.lock:
            deleted=0
            for process_id in process_ids:
                if process_id in self.records:
                    self.records.pop(process_id,None);(self.root/f'{process_id}.json').unlink(missing_ok=True);deleted+=1
            return deleted
