from __future__ import annotations
import os, signal, subprocess, threading, time, uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from .command_builder import CommandBuilder
from .log_capture import LogCapture
from .process_registry import ProcessRegistry
from ..config import LOG_ROOT, PROCESS_STOP_TIMEOUT
from ..path_service import PathService

def now(): return datetime.now(timezone.utc).isoformat()
class ProcessManager:
    def __init__(self,paths:PathService,registry:ProcessRegistry,builder:CommandBuilder): self.paths=paths; self.registry=registry; self.builder=builder; self.live={}; self.logs={}; self.lock=threading.RLock()
    def start(self): self.registry.start(); self.reconcile()
    def reconcile(self):
        for r in self.registry.list():
            if r.get("status")=="RUNNING" and not self._pid_alive(r.get("pid",0)): r.update(status="LOST",ended_at=now()); self.registry.save(r)
    def launch(self,*,session_id="",path,runner="",arguments=None,working_directory="",environment=None,encoding="utf-8",python_executable=""):
        cmd,py=self.builder.build(path,runner,arguments or [],python_executable); cwd=self.paths.resolve(working_directory or str(Path(path).parent),must_exist=True)
        env=os.environ.copy(); env["PYTHONUNBUFFERED"]="1"; env.update({str(k):str(v) for k,v in (environment or {}).items()})
        process_id="proc_"+uuid.uuid4().hex; creationflags=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)
        p=subprocess.Popen(cmd,cwd=str(cwd),env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding=encoding,errors="replace",bufsize=1,shell=False,creationflags=creationflags)
        capture=LogCapture(LOG_ROOT/f"{process_id}.stdout.log",LOG_ROOT/f"{process_id}.stderr.log"); capture.start(p.stdout,p.stderr)
        record={"process_id":process_id,"session_id":session_id,"pid":p.pid,"status":"RUNNING","return_code":None,"started_at":now(),"ended_at":"","command":cmd,"path":path,"runner":runner,"arguments":arguments or [],"working_directory":self.paths.relative(cwd),"python_executable":py,"environment_keys":sorted((environment or {}).keys())}
        with self.lock: self.live[process_id]=p; self.logs[process_id]=capture
        self.registry.save(record); threading.Thread(target=self._watch,args=(process_id,p),daemon=True).start(); return self.status(process_id)
    def _watch(self,process_id,p):
        rc=p.wait(); r=self.registry.get(process_id); r.update(status="EXITED" if rc==0 else "FAILED",return_code=rc,ended_at=now()); self.registry.save(r)
    def status(self,process_id):
        r=self.registry.get(process_id); p=self.live.get(process_id)
        if p and p.poll() is not None: r=self.registry.get(process_id)
        try:
            start=datetime.fromisoformat(r["started_at"]); r["uptime_seconds"]=max(0,(datetime.now(timezone.utc)-start).total_seconds()) if r["status"]=="RUNNING" else None
        except Exception: r["uptime_seconds"]=None
        return r
    def log(self,process_id,**kwargs):
        if process_id in self.logs: return {"process_id":process_id,**self.logs[process_id].get(**kwargs)}
        result={"process_id":process_id}
        for n in ("stdout","stderr"):
            p=LOG_ROOT/f"{process_id}.{n}.log"; result[n]=p.read_text(encoding="utf-8",errors="replace")[-50000:] if p.exists() else ""
        return result
    def tree(self,process_id):
        r=self.status(process_id)
        try:
            import psutil; root=psutil.Process(r["pid"]); children=[{"pid":x.pid,"status":x.status(),"name":x.name()} for x in root.children(recursive=True)]
        except Exception: children=[]
        return {"process_id":process_id,"pid":r["pid"],"children":children}
    def stop(self,process_id,timeout=PROCESS_STOP_TIMEOUT):
        r=self.registry.get(process_id); p=self.live.get(process_id)
        root_pid=int(r["pid"])
        try:
            import psutil
            parent=psutil.Process(root_pid); descendants=parent.children(recursive=True)
        except Exception:
            descendants=[]
        if (not p or p.poll() is not None) and not descendants:return self.status(process_id)
        try:
            if p and p.poll() is None:
                if os.name=="nt": p.send_signal(signal.CTRL_BREAK_EVENT)
                else: p.terminate()
                p.wait(timeout=timeout)
            if descendants:
                import psutil
                [child.terminate() for child in descendants if child.is_running()]
                _,alive=psutil.wait_procs(descendants,timeout=2)
                [child.kill() for child in alive]
        except Exception:
            try:
                import psutil; parent=psutil.Process(root_pid); children=parent.children(recursive=True); [c.terminate() for c in children]; parent.terminate(); _,alive=psutil.wait_procs([*children,parent],timeout=2); [x.kill() for x in alive]
            except Exception:
                if p and p.poll() is None:p.kill()
        r=self.registry.get(process_id); r.update(status="STOPPED",return_code=p.poll() if p else r.get("return_code"),ended_at=now()); self.registry.save(r); return r
    def restart(self,process_id):
        r=self.registry.get(process_id); self.stop(process_id); return self.launch(session_id=r.get("session_id",""),path=r["path"],runner=r.get("runner",""),arguments=r.get("arguments",[]),working_directory=r.get("working_directory",""),python_executable=r.get("python_executable",""))
    def list(self,session_id="",status=""):
        rows=[self.status(r["process_id"]) for r in self.registry.list()]; return [r for r in rows if (not session_id or r.get("session_id")==session_id) and (not status or r.get("status")==status)]
    def delete_finished_records(self,process_ids=None):
        terminal={"EXITED","FAILED","STOPPED","LOST"};selected=set(process_ids or [])
        records=[r for r in self.registry.list() if r.get("status") in terminal and (not selected or r["process_id"] in selected)]
        ids=[r["process_id"] for r in records]
        with self.lock:
            for process_id in ids:self.live.pop(process_id,None);self.logs.pop(process_id,None)
        return self.registry.delete(ids)
    @staticmethod
    def _pid_alive(pid):
        try: os.kill(int(pid),0); return True
        except Exception: return False
