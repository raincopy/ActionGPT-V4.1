from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = Path(os.environ.get("LIQ_MAP_ROOT", str(BASE_DIR.parent))).expanduser().resolve()
ACTGPT_ROOT = Path(os.environ.get("LIQ_ACTGPT_ROOT", str(BASE_DIR))).expanduser().resolve()
ROOTS_CFG = Path(os.environ.get("LIQ_ACTION_ROOTS_CFG", str(BASE_DIR / "liq_analysis_server" / "allowed_roots.cfg"))).expanduser().resolve()
DB_CONNECTIONS_CFG = Path(os.environ.get("LIQ_ACTION_DB_CONNECTIONS_CFG", str(BASE_DIR / "liq_analysis_server" / "db_connections.cfg"))).expanduser().resolve()
WEB_HOSTS_CFG = Path(os.environ.get("LIQ_ACTION_WEB_HOSTS_CFG", str(BASE_DIR / "liq_analysis_server" / "allowed_web_hosts.cfg"))).expanduser().resolve()
DATA_ROOT = Path(os.environ.get("LIQ_ACTION_DATA_ROOT", str(ACTGPT_ROOT / "data"))).resolve()
TASK_ROOT = Path(os.environ.get("LIQ_ACTION_TASK_ROOT", str(DATA_ROOT / "tasks"))).resolve()
PROCESS_ROOT = Path(os.environ.get("LIQ_ACTION_PROCESS_ROOT", str(DATA_ROOT / "processes"))).resolve()
LOG_ROOT = Path(os.environ.get("LIQ_ACTION_LOG_ROOT", str(DATA_ROOT / "logs"))).resolve()
ARTIFACT_ROOT = Path(os.environ.get("LIQ_ACTION_ARTIFACT_ROOT", str(DATA_ROOT / "artifacts"))).resolve()
BROWSER_ROOT = Path(os.environ.get("LIQ_ACTION_BROWSER_ROOT", str(DATA_ROOT / "browser_sessions"))).resolve()

SERVER_HOST = os.environ.get("LIQ_ACTION_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("LIQ_ACTION_PORT", "8012"))
PUBLIC_SERVER_URL = os.environ.get(
    "LIQ_ACTION_PUBLIC_URL",
    "https://subcommissarial-sid-votable.ngrok-free.dev",
).rstrip("/")
API_KEY = os.environ.get("LIQ_ACTION_API_KEY", "").strip()
MAX_WORKERS = int(os.environ.get("LIQ_ACTION_MAX_WORKERS", "6"))
MAX_LOG_CHARS = int(os.environ.get("LIQ_ACTION_MAX_LOG_CHARS", "500000"))
MAX_EXECUTION_OUTPUT_CHARS = int(os.environ.get("LIQ_ACTION_MAX_EXECUTION_OUTPUT", "50000"))
PROCESS_STOP_TIMEOUT = float(os.environ.get("LIQ_ACTION_PROCESS_STOP_TIMEOUT", "10"))
BROWSER_TIMEOUT_MS = int(os.environ.get("LIQ_ACTION_BROWSER_TIMEOUT_MS", "20000"))
BROWSER_HEADLESS = os.environ.get("LIQ_ACTION_BROWSER_HEADLESS", "false").lower() in {"1", "true", "yes"}
ARTIFACT_TTL_HOURS = int(os.environ.get("LIQ_ACTION_ARTIFACT_TTL_HOURS", "72"))
CAPTURE_ON_FAILURE = os.environ.get("LIQ_ACTION_CAPTURE_ON_FAILURE", "true").lower() in {"1", "true", "yes"}
ALLOWED_WEB_HOSTS = {x.strip().lower() for x in os.environ.get("LIQ_ACTION_ALLOWED_WEB_HOSTS", "127.0.0.1,localhost").split(",") if x.strip()}

POSTGRES_DEFAULTS = {
    "host": os.environ.get("LIQ_PGHOST", os.environ.get("PGHOST", "127.0.0.1")),
    "port": int(os.environ.get("LIQ_PGPORT", os.environ.get("PGPORT", "5432"))),
    "dbname": os.environ.get("LIQ_PGDATABASE", os.environ.get("PGDATABASE", "liq_map_db")),
    "user": os.environ.get("LIQ_PGUSER", os.environ.get("PGUSER", "liq_map_user")),
    "password": os.environ.get("LIQ_PGPASSWORD", os.environ.get("PGPASSWORD", "2848")),
}

VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON_EXECUTABLE = str(VENV_PYTHON if VENV_PYTHON.exists() else Path(os.environ.get("LIQ_ACTION_PYTHON", sys.executable)))
TASK_STATUS_DIRS = {"WAITING": "0010", "RUNNING": "0020", "COMPLETED": "0030", "FAILED": "0040"}
EXCLUDED_NAMES = {
    "ActGpt", "ActGPTEx", "__pycache__", ".git", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".venv", "venv", "node_modules",
}

def ensure_data_dirs() -> None:
    for path in (TASK_ROOT, PROCESS_ROOT, LOG_ROOT, ARTIFACT_ROOT, BROWSER_ROOT):
        path.mkdir(parents=True, exist_ok=True)
    for name in TASK_STATUS_DIRS.values():
        (TASK_ROOT / name).mkdir(parents=True, exist_ok=True)
