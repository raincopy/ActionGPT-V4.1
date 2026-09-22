from __future__ import annotations
import logging
import traceback
from contextlib import asynccontextmanager
from fastapi import Depends,FastAPI,Header,HTTPException,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse,JSONResponse
from . import __version__
from .config import API_KEY,PROJECT_ROOT,PUBLIC_SERVER_URL
from .models import ApiResponse,FileApiRequest,FileApiResponse,DbApiRequest,ExecutionApiRequest
from .file_service import FileConflictError
from .runtime import initialize_runtime,stop_runtime,file_service,db_service,execution_service,task_manager,artifact_service

@asynccontextmanager
async def lifespan(_app):
    initialize_runtime();yield;stop_runtime()
app=FastAPI(title="Liq-analysis Action GPT Server",version=__version__,description="Liq-Map 전용 파일·DB·실행 API 서버.",servers=[{"url":PUBLIC_SERVER_URL}] if PUBLIC_SERVER_URL else None,lifespan=lifespan)
logger=logging.getLogger("liq_analysis_server.api")
def require_key(x_api_key:str|None=Header(default=None)):
    if API_KEY and x_api_key!=API_KEY:raise HTTPException(401,"invalid API key")
def ok(api,c,cmd,result=None,status="COMPLETED",task_id="",request=None,progress=None,current_step=""):
    return {
        "success":True,
        "task_id":task_id,
        "session_id":getattr(request,"session_id","") if request else "",
        "request_id":getattr(request,"request_id","") if request else "",
        "api_name":api,
        "api":api,
        "category_code":c,
        "command_code":cmd,
        "status":status,
        "progress":progress if progress is not None else (100 if status=="COMPLETED" else 0),
        "current_step":current_step or ("완료" if status=="COMPLETED" else "접수"),
        "result":result,
        "error":None,
        "error_message":"",
    }
def _request_summary(api_name,r):
    summary={"api":api_name,"session_id":r.session_id,"category_code":r.category_code,"command_code":r.command_code}
    for name in ("path","source_path","target_path","new_name","task_id","process_id","browser_session_id","window_id","artifact_id","url"):
        value=getattr(r,name,None)
        if value not in (None,""):summary[name]=value
    if getattr(r,"content",""):summary["content_chars"]=len(r.content)
    if getattr(r,"sql",""):summary["sql_chars"]=len(r.sql)
    if getattr(r,"arguments",None):summary["arguments"]=r.arguments
    if getattr(r,"environment",None):summary["environment_keys"]=sorted(r.environment)
    return summary
def guarded(call,api_name,r):
    context=_request_summary(api_name,r)
    try:return call()
    except FileNotFoundError as e:
        logger.error("API 명령 실패 status=404 request=%s error=%s",context,e);raise HTTPException(404,{"code":"NOT_FOUND","message":str(e)}) from e
    except (ValueError,FileExistsError,NotADirectoryError,IsADirectoryError) as e:
        logger.error("API 명령 실패 status=400 request=%s error=%s",context,e);raise HTTPException(400,{"code":"INVALID_REQUEST","message":str(e)}) from e
    except FileConflictError as e:
        logger.error("API 명령 충돌 status=409 request=%s error=%s",context,e);raise HTTPException(409,{"code":"FILE_CHANGED","message":str(e)}) from e
    except HTTPException as e:
        logger.error("API 명령 실패 status=%s request=%s error=%s",e.status_code,context,e.detail);raise
    except Exception as e:
        logger.error("API 명령 실패 status=500 request=%s error=%s: %s\n%s",context,type(e).__name__,e,traceback.format_exc());raise HTTPException(500,{"code":"INTERNAL_ERROR","message":f"{type(e).__name__}: {e}"}) from e

@app.exception_handler(HTTPException)
async def http_error_handler(request:Request,exc:HTTPException):
    detail=exc.detail if isinstance(exc.detail,dict) else {"code":f"HTTP_{exc.status_code}","message":str(exc.detail)}
    try:
        payload=await request.json()
    except Exception:
        payload={}
    api_name={"/api/file":"FILE_API","/api/db":"DB_API","/api/execution":"EXECUTION_API"}.get(request.url.path,"")
    body={
        "success":False,"task_id":"","session_id":str(payload.get("session_id", "")),"request_id":str(payload.get("request_id", "")),
        "api_name":api_name,"api":api_name,"category_code":str(payload.get("category_code", "")),"command_code":str(payload.get("command_code", "")),
        "status":"FAILED","progress":100,"current_step":"실패","result":None,"error":detail,"error_message":str(detail.get("message", "")),
    }
    return JSONResponse(status_code=exc.status_code,content=body)

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request:Request,exc:RequestValidationError):
    errors=exc.errors();logger.error("API 요청 검증 실패 status=422 path=%s errors=%s",request.url.path,errors)
    return JSONResponse(status_code=422,content={"success":False,"task_id":"","session_id":"","request_id":"","api_name":"","api":"","category_code":"","command_code":"","status":"FAILED","progress":100,"current_step":"요청 검증 실패","result":None,"error":{"code":"VALIDATION_ERROR","message":"요청 필드 검증에 실패했다","detail":errors},"error_message":"요청 필드 검증에 실패했다"})

@app.post("/api/file",operation_id="fileApi",summary="FILE_API",description="파일 조회·읽기·생성·수정·이동·삭제·원복을 처리한다.",response_model=FileApiResponse,dependencies=[Depends(require_key)])
def file_api(r:FileApiRequest):
    c,cmd=r.category_code.upper(),r.command_code.upper()
    def run():
        if (c,cmd)!=("STRUCTURE","LIST_ROOT") and not r.path.strip():raise ValueError("path 값이 필요하다")
        immediate={("STRUCTURE","LIST_ROOT"):lambda:file_service.list_root(),("STRUCTURE","LIST_DIRECTORY"):lambda:file_service.list_directory(r.path),("STRUCTURE","GET_PATH_INFO"):lambda:file_service.get_path_info(r.path),("READ","READ_FILE"):lambda:file_service.read_file(r.path,r.max_chars or 1000000),("READ","READ_FILE_CHUNK"):lambda:file_service.read_file_chunk(r.path,r.start_line or 1,r.line_count or 200,r.max_chars or 60000)}
        if (c,cmd) in immediate:return ok("FILE_API",c,cmd,immediate[(c,cmd)](),request=r)
        if (c,cmd) in {("WRITE","CREATE_FILE"),("WRITE","UPDATE_FILE")} and "content" not in r.model_fields_set:raise ValueError("content 필드가 필요하다")
        if (c,cmd) in {("MUTATE","MOVE_FILE"),("MUTATE","MOVE_DIRECTORY")} and (not r.source_path or not r.target_path):raise ValueError("source_path와 target_path가 필요하다")
        if (c,cmd) in {("MUTATE","RENAME_FILE"),("MUTATE","RENAME_DIRECTORY")} and not r.new_name:raise ValueError("new_name 값이 필요하다")
        handlers={("WRITE","CREATE_FILE"):lambda:file_service.create_file(r.path,r.content),("WRITE","UPDATE_FILE"):lambda:file_service.update_file(r.path,r.content,r.expected_sha256),("MUTATE","DELETE_FILE"):lambda:file_service.delete_file(r.path),("MUTATE","CREATE_DIRECTORY"):lambda:file_service.create_directory(r.path),("MUTATE","DELETE_DIRECTORY"):lambda:file_service.delete_directory(r.path),("MUTATE","MOVE_FILE"):lambda:file_service.move_file(r.source_path,r.target_path),("MUTATE","MOVE_DIRECTORY"):lambda:file_service.move_directory(r.source_path,r.target_path),("MUTATE","RENAME_FILE"):lambda:file_service.rename_file(r.path,r.new_name),("MUTATE","RENAME_DIRECTORY"):lambda:file_service.rename_directory(r.path,r.new_name),("RESTORE","RESTORE_LATEST_FILE"):lambda:file_service.restore_latest_file(r.path)}
        if (c,cmd) not in handlers:raise ValueError(f"지원하지 않는 FILE_API 명령이다: {c}/{cmd}")
        record=task_manager.execute_inline(session_id=r.session_id,request_id=r.request_id,api_name="FILE_API",category_code=c,command_code=cmd,target=r.model_dump(),handler=lambda progress:handlers[(c,cmd)]())
        if record.get("status")=="FAILED":
            failure=record.get("error") or {}
            raise HTTPException(409,{"code":"REQUEST_ALREADY_FAILED","message":failure.get("message","같은 request_id의 이전 FILE 작업이 실패했다"),"detail":{"task_id":record.get("task_id","")}})
        return ok("FILE_API",c,cmd,record.get("result"),record["status"],record["task_id"],r,record.get("progress"),record.get("current_step",""))
    return guarded(run,"FILE_API",r)

@app.post("/api/db",operation_id="dbApi",summary="DB_API",description="PostgreSQL 구조·데이터 조회와 실행·검증을 처리한다.",response_model=ApiResponse,dependencies=[Depends(require_key)])
def db_api(r:DbApiRequest):
    c,cmd=r.category_code.upper(),r.command_code.upper()
    def run():
        h={("STRUCTURE","LIST_TABLES"):lambda:db_service.list_tables(r.target),("STRUCTURE","LIST_COLUMNS"):lambda:db_service.list_columns(r.target),("READ","READ_DATA"):lambda:db_service.read_data(r.target,r.options),("READ","EXECUTE_SELECT"):lambda:db_service.execute_select(r.sql,r.target),("EXECUTE","EXECUTE_DDL"):lambda:db_service.execute_ddl(r.sql,r.target),("EXECUTE","EXECUTE_DML"):lambda:db_service.execute_dml(r.sql,r.target),("VERIFY","VERIFY_TABLE"):lambda:db_service.verify_table(r.target,r.options),("VERIFY","VERIFY_COLUMNS"):lambda:db_service.verify_columns(r.target,r.options),("VERIFY","VERIFY_DATA"):lambda:db_service.verify_data(r.sql,r.target,r.options)}
        if (c,cmd) not in h:raise ValueError(f"지원하지 않는 DB_API 명령이다: {c}/{cmd}")
        return ok("DB_API",c,cmd,h[(c,cmd)](),request=r)
    return guarded(run,"DB_API",r)

@app.post("/api/execution",operation_id="executionApi",summary="EXECUTION_API",description="실행·프로세스·브라우저·Windows UI·검증을 처리한다.",response_model=ApiResponse,dependencies=[Depends(require_key)])
def execution_api(r:ExecutionApiRequest):
    c,cmd=r.category_code.upper(),r.command_code.upper()
    def run():
        x=execution_service.dispatch(r)
        if isinstance(x,dict) and "task_id" in x and "status" in x and isinstance(x.get("result"),dict) and x["result"].get("accepted") is True:return ok("EXECUTION_API",c,cmd,x.get("result"),x["status"],x["task_id"],r)
        return ok("EXECUTION_API",c,cmd,x,request=r)
    return guarded(run,"EXECUTION_API",r)

@app.get("/health",include_in_schema=False)
def health():return {"status":"ok","version":__version__,"project_root":str(PROJECT_ROOT),"active_tasks":len([x for x in task_manager.list() if x["status"] in {"WAITING","RUNNING"}])}
@app.get("/artifacts/{artifact_id}",include_in_schema=False)
def artifact_file(artifact_id:str,expires:int,signature:str):
    if not artifact_service.verify(artifact_id,expires,signature):raise HTTPException(403,"invalid or expired artifact signature")
    path,meta=artifact_service.file(artifact_id);return FileResponse(path,media_type=meta["mime_type"],filename=meta["filename"])
