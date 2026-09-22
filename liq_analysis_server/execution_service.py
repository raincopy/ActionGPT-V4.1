from __future__ import annotations
import os,subprocess
from typing import Any
from .config import MAX_EXECUTION_OUTPUT_CHARS

class ExecutionFailure(RuntimeError):
    def __init__(self,message,result):super().__init__(message);self.result=result
class ExecutionService:
    def __init__(self,task_manager,builder,processes,probes,browsers,windows,artifacts,verification,paths): self.tasks=task_manager;self.builder=builder;self.processes=processes;self.probes=probes;self.browsers=browsers;self.windows=windows;self.artifacts=artifacts;self.verification=verification;self.paths=paths
    def dispatch(self,request):
        c=request.category_code.strip().upper(); cmd=request.command_code.strip().upper(); p=self._payload(request)
        self._validate(c,cmd,p)
        if c=="RUN" and cmd in {"RUN_PYTHON","RUN_BATCH","RUN_SCRIPT"}:return self._async(request,lambda progress:self._oneshot(p,progress),c,cmd)
        if c=="RESULT":
            if cmd=="GET_EXECUTION_RESULT":return self.get_result(request.task_id)
            if cmd=="GET_EXECUTION_ERROR":return self.get_error(request.task_id)
            raise ValueError(f"지원하지 않는 RESULT 명령이다: {cmd}")
        if c=="PROCESS":
            if cmd=="START_PROCESS":return self._async(request,lambda progress:self.processes.launch(**self._launch(p)),c,cmd)
            if cmd=="STOP_PROCESS":return self._async(request,lambda progress:self.processes.stop(p["process_id"],p.get("timeout_seconds") or 10),c,cmd)
            if cmd=="RESTART_PROCESS":return self._async(request,lambda progress:self.processes.restart(p["process_id"]),c,cmd)
            if cmd=="GET_PROCESS_STATUS":return self.processes.status(p["process_id"])
            if cmd=="GET_PROCESS_LOG":return self.processes.log(p["process_id"],stream=p.get("value") or p.get("stream","both"),tail_lines=p.get("tail_lines",200),since_offset=p.get("since_offset"),max_chars=p.get("max_chars",50000))
            if cmd=="GET_PROCESS_TREE":return self.processes.tree(p["process_id"])
            if cmd=="LIST_PROCESSES":return {"processes":self.processes.list(p.get("session_id",""),p.get("status",""))}
        if c=="PROBE":return self._probe(request,p,c,cmd)
        if c=="BROWSER":
            async_commands={"START_BROWSER","OPEN_PAGE","WAIT_FOR_ELEMENT"}
            return self._async(request,lambda progress:self.browsers.execute(cmd,p),c,cmd) if cmd in async_commands else self.browsers.execute(cmd,p)
        if c=="WINDOWS_UI":return self._windows(request,p,c,cmd)
        if c=="ARTIFACT":
            if cmd=="LIST_ARTIFACTS":return {"artifacts":self.artifacts.list(type=p.get("type",""),process_id=p.get("process_id",""),session_id=p.get("session_id",""))}
            if cmd=="GET_ARTIFACT_INFO":return self.artifacts.info(p["artifact_id"])
            if cmd=="DELETE_ARTIFACT":return self.artifacts.delete(p["artifact_id"])
        if c=="VERIFY" and cmd=="VERIFY_VALUE":return self.verification.verify(p.get("actual",p.get("value")),request.assertions or p.get("assertions",[]))
        raise ValueError(f"지원하지 않는 EXECUTION_API 명령이다: {c}/{cmd}")
    @staticmethod
    def _validate(c,cmd,p):
        def need(*names):
            missing=[name for name in names if p.get(name) in (None,"",[],{})]
            if missing:raise ValueError(f"{c}/{cmd} 필수 필드가 없다: {', '.join(missing)}")
        if c=="RUN":need("path")
        elif c=="RESULT":need("task_id")
        elif c=="PROCESS":
            if cmd=="START_PROCESS":need("path")
            elif cmd in {"GET_PROCESS_STATUS","GET_PROCESS_LOG","GET_PROCESS_TREE","STOP_PROCESS","RESTART_PROCESS"}:need("process_id")
        elif c=="PROBE":
            if cmd in {"CHECK_TCP_PORT","WAIT_FOR_TCP_PORT"}:need("port")
            elif cmd in {"CHECK_HTTP","WAIT_FOR_HTTP"}:need("url")
            elif cmd in {"CHECK_LOG_TEXT","WAIT_FOR_LOG_TEXT"}:need("process_id")
            elif cmd=="GET_APPLICATION_STATE":need("probe")
        elif c=="BROWSER":
            if cmd!="START_BROWSER":need("browser_session_id")
            if cmd=="OPEN_PAGE":need("url")
            if cmd in {"CLICK_ELEMENT","FILL_INPUT","SELECT_OPTION","CHECK_ELEMENT","UNCHECK_ELEMENT","WAIT_FOR_ELEMENT","GET_ELEMENT_TEXT","GET_ELEMENT_VALUE","GET_TABLE_DATA"}:need("locator")
        elif c=="WINDOWS_UI":
            if cmd=="WAIT_FOR_WINDOW":need("process_id")
            elif cmd!="LIST_WINDOWS":need("window_id")
            if cmd in {"CLICK_CONTROL","SET_CONTROL_TEXT","SELECT_CONTROL","GET_CONTROL_VALUE"}:need("control")
        elif c=="ARTIFACT" and cmd!="LIST_ARTIFACTS":need("artifact_id")
        elif c=="VERIFY" and cmd=="VERIFY_VALUE":need("assertions")
    def _probe(self,r,p,c,cmd):
        calls={"CHECK_TCP_PORT":lambda:self.probes.tcp(p.get("host") or "127.0.0.1",p["port"]),"CHECK_HTTP":lambda:self.probes.http(p["url"],p.get("expected_status",200)),"CHECK_LOG_TEXT":lambda:self.probes.log(p["process_id"],str(p.get("text") or p.get("value") or ""),p.get("regex","")),"GET_APPLICATION_STATE":lambda:self.probes.application_state(p.get("probe") or p)}
        base=cmd.replace("WAIT_FOR_","CHECK_")
        if cmd.startswith("WAIT_FOR_"):
            if base not in calls:raise ValueError(f"지원하지 않는 probe다: {cmd}")
            return self._async(r,lambda progress:self.probes.wait(calls[base],p.get("timeout_seconds") or 20,p.get("interval_seconds",.25)),c,cmd)
        if cmd not in calls:raise ValueError(f"지원하지 않는 probe다: {cmd}")
        return calls[cmd]()
    def _windows(self,r,p,c,cmd):
        async_commands={"WAIT_FOR_WINDOW"}
        def call():
            if cmd=="LIST_WINDOWS":return {"windows":self.windows.list_windows(p.get("process_id",""))}
            if cmd=="WAIT_FOR_WINDOW":return self.windows.wait_for_window(p["process_id"],str(p.get("value") or p.get("title") or ""),p.get("regex",""),p.get("timeout_seconds") or 20)
            if cmd=="GET_WINDOW_STATE":return self.windows.state(p["window_id"])
            if cmd=="GET_CONTROL_TREE":return self.windows.tree(p["window_id"],p.get("max_depth",6),p.get("max_nodes",500))
            if cmd=="CLICK_CONTROL":return self.windows.click(p["window_id"],p.get("control"))
            if cmd=="SET_CONTROL_TEXT":return self.windows.set_text(p["window_id"],p.get("control"),p.get("input_text",""))
            if cmd=="SELECT_CONTROL":return self.windows.select(p["window_id"],p.get("control"),p.get("value"))
            if cmd=="GET_CONTROL_VALUE":return self.windows.value(p["window_id"],p.get("control"))
            if cmd=="PRESS_KEYS":return self.windows.press(p["window_id"],p.get("control"),p.get("key",""))
            if cmd=="TAKE_WINDOW_SCREENSHOT":return self.windows.screenshot(p["window_id"],p.get("control"))
            if cmd=="CLOSE_WINDOW":return self.windows.close_window(p["window_id"])
            raise ValueError(f"지원하지 않는 WINDOWS_UI 명령이다: {cmd}")
        return self._async(r,lambda progress:call(),c,cmd) if cmd in async_commands else call()
    def _oneshot(self,p,progress):
        progress(10,"명령 구성");cmd,py=self.builder.build(p["path"],p.get("runner","") or ("python" if p.get("command_code")=="RUN_PYTHON" else "batch" if p.get("command_code")=="RUN_BATCH" else ""),p.get("arguments",[]),p.get("python_executable",""));cwd=self.paths.resolve(p.get("working_directory") or os.path.dirname(p["path"]) or ".",must_exist=True);env=os.environ.copy();env.update({str(k):str(v) for k,v in p.get("environment",{}).items()});progress(30,"실행");r=subprocess.run(cmd,cwd=str(cwd),env=env,capture_output=True,text=True,encoding=p.get("encoding","utf-8"),errors="replace",timeout=p.get("timeout_seconds"),shell=False);result={"command":cmd,"working_directory":str(cwd),"python_executable":py,"return_code":r.returncode,"stdout":r.stdout[:MAX_EXECUTION_OUTPUT_CHARS],"stderr":r.stderr[:MAX_EXECUTION_OUTPUT_CHARS]};
        if r.returncode:raise ExecutionFailure(f"프로세스가 {r.returncode} 코드로 종료되었다",result)
        return result
    def _async(self,r,handler,c,cmd):
        submitted=self.tasks.submit(session_id=r.session_id,request_id=r.request_id,api_name="EXECUTION_API",category_code=c,command_code=cmd,target=self._payload(r),handler=handler);return {"status":submitted["status"],"task_id":submitted["task_id"],"result":{"accepted":True,"reused":submitted.get("reused",False)}}
    def get_result(self,tid):return self.tasks.get(tid)
    def get_error(self,tid):
        x=self.tasks.get(tid);return {"task_id":tid,"status":x["status"],"error":x.get("error"),"result":x.get("result")}
    @staticmethod
    def _payload(r):
        p={**r.options,**r.target,**r.model_dump(exclude_none=True)};p["command_code"]=r.command_code.strip().upper()
        for name in ("locator","control","probe"):
            if p.get(name) is not None and hasattr(p[name],"model_dump"):p[name]=p[name].model_dump()
        return p
    @staticmethod
    def _launch(p):return {k:p[k] for k in ("session_id","path","runner","arguments","working_directory","environment","encoding","python_executable") if k in p}
