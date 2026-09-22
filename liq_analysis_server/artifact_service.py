from __future__ import annotations
import hashlib,hmac,json,mimetypes,secrets,time,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Any
from .config import ARTIFACT_ROOT,ARTIFACT_TTL_HOURS

class ArtifactService:
    def __init__(self,root:Path=ARTIFACT_ROOT,ttl_hours=ARTIFACT_TTL_HOURS): self.root=root.resolve(); self.ttl_hours=ttl_hours; self.secret=secrets.token_bytes(32)
    def start(self): self.root.mkdir(parents=True,exist_ok=True); self.cleanup()
    def create_bytes(self,data:bytes,*,kind:str,suffix:str,source:dict[str,Any]|None=None):
        aid="art_"+uuid.uuid4().hex; path=self.root/f"{aid}{suffix}"; path.write_bytes(data); created=datetime.now(timezone.utc); meta={"artifact_id":aid,"type":kind,"filename":path.name,"size":len(data),"sha256":hashlib.sha256(data).hexdigest(),"mime_type":mimetypes.guess_type(path.name)[0] or "application/octet-stream","created_at":created.isoformat(),"expires_at":(created+timedelta(hours=self.ttl_hours)).isoformat(),**(source or {})}; self._meta(aid).write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8"); return {**meta,"signed_url":self.signed_url(aid)}
    def create_text(self,text,*,kind="text",suffix=".txt",source=None): return self.create_bytes(text.encode("utf-8"),kind=kind,suffix=suffix,source=source)
    def info(self,aid):
        p=self._meta(aid)
        if not p.exists(): raise FileNotFoundError(f"아티팩트를 찾을 수 없다: {aid}")
        meta=json.loads(p.read_text(encoding="utf-8")); return {**meta,"signed_url":self.signed_url(aid)}
    def list(self,**filters):
        rows=[]
        for p in self.root.glob("*.json"):
            try: m=json.loads(p.read_text(encoding="utf-8"));
            except Exception: continue
            if all(not v or m.get(k)==v for k,v in filters.items()): rows.append(m)
        return sorted(rows,key=lambda x:x["created_at"],reverse=True)
    def delete(self,aid):
        m=self.info(aid); (self.root/m["filename"]).unlink(missing_ok=True); self._meta(aid).unlink(missing_ok=True); return {"deleted":aid}
    def signed_url(self,aid,ttl=900):
        exp=int(time.time())+ttl; sig=hmac.new(self.secret,f"{aid}:{exp}".encode(),hashlib.sha256).hexdigest(); return f"/artifacts/{aid}?expires={exp}&signature={sig}"
    def verify(self,aid,expires,signature): return int(expires)>=int(time.time()) and hmac.compare_digest(signature,hmac.new(self.secret,f"{aid}:{expires}".encode(),hashlib.sha256).hexdigest())
    def file(self,aid):
        m=self.info(aid); p=(self.root/m["filename"]).resolve()
        if self.root not in p.parents: raise ValueError("잘못된 아티팩트 경로")
        return p,m
    def cleanup(self):
        now=datetime.now(timezone.utc); count=0
        for m in self.list():
            try:
                if datetime.fromisoformat(m["expires_at"])<now: self.delete(m["artifact_id"]); count+=1
            except Exception: continue
        return count
    def _meta(self,aid):
        if not aid.startswith("art_") or not aid[4:].isalnum(): raise ValueError("잘못된 artifact_id")
        return self.root/f"{aid}.json"

