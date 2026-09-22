from __future__ import annotations
import json,re,socket,time,urllib.error,urllib.request
from pathlib import Path
from urllib.parse import urlparse
from typing import Any
from ..config import ALLOWED_WEB_HOSTS
from ..path_service import PathService

class ProbeService:
    def __init__(self,paths:PathService,processes,web_hosts=None): self.paths=paths; self.processes=processes; self.web_hosts=web_hosts
    def validate_url(self,url):
        parsed=urlparse(url); host=(parsed.hostname or "").lower()
        allowed=self.web_hosts.hosts if self.web_hosts else ALLOWED_WEB_HOSTS
        if parsed.scheme not in {"http","https"} or host not in allowed: raise ValueError(f"허용되지 않은 URL이다: {url}")
    def tcp(self,host,port):
        allowed=self.web_hosts.hosts if self.web_hosts else ALLOWED_WEB_HOSTS
        if host.lower() not in allowed: raise ValueError("허용되지 않은 host다")
        try:
            with socket.create_connection((host,int(port)),timeout=2): return {"verified":True,"host":host,"port":port}
        except OSError as exc: return {"verified":False,"host":host,"port":port,"error":str(exc)}
    def http(self,url,expected_status=200):
        self.validate_url(url)
        try:
            with urllib.request.urlopen(url,timeout=3) as r: body=r.read(2000).decode("utf-8",errors="replace"); status=r.status
            return {"verified":status==int(expected_status),"status_code":status,"body":body,"url":url}
        except urllib.error.HTTPError as exc: return {"verified":exc.code==int(expected_status),"status_code":exc.code,"error":str(exc),"url":url}
        except Exception as exc: return {"verified":False,"error":str(exc),"url":url}
    def wait(self,call,timeout=20,interval=.25):
        end=time.monotonic()+float(timeout); last={}
        while time.monotonic()<end:
            last=call()
            if last.get("verified"): return last
            time.sleep(float(interval))
        return {**last,"timed_out":True}
    def log(self,process_id,text="",regex=""):
        data=self.processes.log(process_id,stream="both",tail_lines=5000,max_chars=500000); combined=data.get("stdout","")+data.get("stderr",""); found=bool(re.search(regex,combined)) if regex else text in combined
        return {"verified":found,"process_id":process_id,"text":text,"regex":regex}
    def application_state(self,probe:dict[str,Any]):
        kind=probe.get("type")
        if kind=="json_file": return {"verified":True,"state":json.loads(self.paths.resolve(probe["path"],must_exist=True).read_text(encoding="utf-8"))}
        if kind=="state_url":
            result=self.http(probe["url"],probe.get("expected_status",200))
            if result.get("verified"):
                try: result["state"]=json.loads(result["body"])
                except Exception: result["state"]=result["body"]
            return result
        raise ValueError("json_file 또는 state_url probe가 필요하다")
