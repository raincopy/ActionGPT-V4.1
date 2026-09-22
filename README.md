# Liq-analysis Action GPT Server v4.1

`ActGPTEx`는 Liq-Map 로컬 개발 환경을 대상으로 파일·DB·프로세스·브라우저·Windows UI의 실행-관찰-조작-검증 루프를 제공한다.

## 공개 Action API

- `POST /api/file` (`fileApi`)
- `POST /api/db` (`dbApi`)
- `POST /api/execution` (`executionApi`)

상태 확인과 서명된 아티팩트 다운로드 경로는 OpenAPI에서 제외된다. Action API는 세 개로 유지하며 세부 동작은 `category_code`와 `command_code`로 선택한다.

## 실행

```bat
run_action_server.bat
```

서버와 관리 UI를 함께 실행하려면 다음을 사용한다.

```bat
run_action_Liq_editor.bat
```

Action GPT에 등록할 OpenAPI 주소는 `https://subcommissarial-xxx-xxx.ngrok-free.dev/openapi.json` 형태 로 만들어야 한다. 
이다. OpenAPI의 `servers` 기준 URL도 `(https://subcommissarial-xxx-xxx.ngrok-free.dev)`로 설정된다. FastAPI는 기본적으로 `0.0.0.0:8012`에서 수신하며 ngrok이 이 로컬 포트로 전달해야 한다. 기본 작업 루트는 `C:\Project\Myproject` 로 할수 있고, 서버 보호 경로는 `C:\Project\ActGPT4.1`이다.

## 주요 EXECUTION 명령

- 기존 호환: `RUN_PYTHON`, `RUN_BATCH`, `RUN_SCRIPT`, `GET_EXECUTION_RESULT`, `GET_EXECUTION_ERROR`
- 프로세스: `START_PROCESS`, `GET_PROCESS_STATUS`, `GET_PROCESS_LOG`, `GET_PROCESS_TREE`, `STOP_PROCESS`, `RESTART_PROCESS`, `LIST_PROCESSES`
- Probe: TCP, HTTP, 로그 문구, JSON/상태 URL 확인 및 대기
- 브라우저: 세션 시작, 페이지 열기, locator 기반 클릭·입력·선택·조회, 콘솔·네트워크 오류, 스크린샷
- Windows UI: 관리 PID와 자식 PID의 창 탐색, 컨트롤 트리, 클릭·입력·선택·조회, 키 입력, 스크린샷
- 아티팩트와 검증: 목록·정보·삭제, 구조화 assertion 실행

## 검증

```bat
C:\Project\.venv\Scripts\python.exe -m pytest -q
```

테스트에는 일회성 실행, 실시간 로그, 다중 worker, 로컬 Chromium 자동화, 네이티브 Windows UI Automation과 스크린샷 생성이 포함된다.
