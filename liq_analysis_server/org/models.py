from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

class LocatorSpec(BaseModel):
    by: Literal["css", "text", "role", "label", "placeholder", "testid", "xpath"] = "css"
    value: str = ""
    role: str = ""
    name: str = ""
    exact: bool = False
    nth: int | None = None

class ControlLocatorSpec(BaseModel):
    automation_id: str = ""
    title: str = ""
    control_type: str = ""
    class_name: str = ""
    found_index: int = 0
    control_path: list[int] = Field(default_factory=list)

class ProbeSpec(BaseModel):
    type: Literal["process", "tcp", "http", "log", "json_file", "state_url"]
    host: str = "127.0.0.1"
    port: int | None = None
    url: str = ""
    path: str = ""
    expected_status: int = 200
    text: str = ""
    regex: str = ""
    timeout_seconds: float = 20
    interval_seconds: float = 0.25

class AssertionSpec(BaseModel):
    field: str = ""
    operator: Literal["equals", "not_equals", "contains", "not_contains", "regex", "exists", "not_exists", "empty", "not_empty", "gt", "gte", "lt", "lte"] = "equals"
    expected: Any = None
    case_sensitive: bool = True

class ViewportSpec(BaseModel):
    width: int = Field(default=1440, ge=320, le=7680)
    height: int = Field(default=1000, ge=240, le=4320)

class BaseApiRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    session_id: str = ""
    request_id: str = ""
    category_code: str
    command_code: str
    target: dict[str, Any] = Field(default_factory=dict)
    content: str = ""
    options: dict[str, Any] = Field(default_factory=dict)

class FileApiRequest(BaseApiRequest):
    path: str = Field(default=".", min_length=1, description="C:\\Project\\Liq-Map 기준 상대 경로. LIST_ROOT는 '.'")
    source_path: str = Field(default="", description="MOVE 계열 원본 상대 경로")
    target_path: str = Field(default="", description="MOVE 계열 대상 상대 경로")
    new_name: str = Field(default="", description="RENAME 계열의 새 파일명 또는 디렉토리명")
    start_line: int | None = Field(default=None, ge=1, description="READ_FILE_CHUNK 시작 줄(1부터)")
    line_count: int | None = Field(default=None, ge=1, le=5000, description="READ_FILE_CHUNK 최대 줄 수")
    max_chars: int | None = Field(default=None, ge=1, le=5_000_000, description="READ 응답 최대 문자 수")
    expected_sha256: str = Field(default="", description="UPDATE_FILE 선택적 동시성 보호용 READ 시점 SHA-256")

class DbApiRequest(BaseApiRequest):
    sql: str = ""

class ExecutionApiRequest(BaseApiRequest):
    path: str = "."
    task_id: str = ""
    process_id: str = ""
    browser_session_id: str = ""
    window_id: str = ""
    artifact_id: str = ""
    runner: str = ""
    arguments: list[str] = Field(default_factory=list)
    working_directory: str = ""
    timeout_seconds: float | None = None
    timeout_ms: int | None = None
    encoding: str = "utf-8"
    python_executable: str = ""
    environment: dict[str, Any] = Field(default_factory=dict)
    host: str = ""
    port: int | None = None
    url: str = ""
    value: Any = None
    input_text: str = ""
    key: str = ""
    locator: LocatorSpec | None = None
    control: ControlLocatorSpec | None = None
    probe: ProbeSpec | None = None
    assertions: list[AssertionSpec] = Field(default_factory=list)
    capture_on_failure: bool | None = None
    viewport: ViewportSpec | None = Field(default=None, description="START_BROWSER 브라우저 viewport")

class ApiError(BaseModel):
    code: str
    message: str
    detail: Any = None

class FileResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = ""
    path: str = ""
    type: str = ""
    content: str = ""
    text: str = Field(default="", description="v0.2 호환용 content 별칭")
    size_bytes: int | None = None
    content_chars: int | None = None
    line_count: int | None = None
    start_line: int | None = None
    end_line: int | None = None
    returned_line_count: int | None = None
    total_line_count: int | None = None
    complete: bool | None = None
    truncated: bool | None = None
    has_more: bool | None = None
    next_start_line: int | None = None
    sha256: str = ""
    modified_at: str = ""
    backup_path: str = ""
    exists: bool | None = None
    entries: list[dict[str, Any]] = Field(default_factory=list)
    entry_count: int | None = None
    children: list[dict[str, Any]] = Field(default_factory=list)
    deleted: str = ""
    created: bool | None = None
    moved: bool | None = None
    renamed: bool | None = None
    restored: bool | None = None
    source_path: str = ""
    target_path: str = ""
    source_exists: bool | None = None
    target_exists: bool | None = None

class ApiResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    success: bool = True
    task_id: str = ""
    session_id: str = ""
    request_id: str = ""
    api_name: str
    api: str = Field(default="", description="v0.2 호환용 api_name 별칭")
    category_code: str
    command_code: str
    status: Literal["WAITING", "RUNNING", "COMPLETED", "FAILED"]
    progress: int = 100
    current_step: str = "완료"
    result: Any = None
    error: ApiError | None = None
    error_message: str = Field(default="", description="v0.2 호환용 오류 문자열")

class FileApiResponse(ApiResponse):
    result: FileResult = Field(default_factory=FileResult)
