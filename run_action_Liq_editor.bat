@echo off
setlocal
set "LIQ_PGHOST=127.0.0.1"
set "LIQ_PGPORT=5432"
set "LIQ_PGDATABASE=liq_map_db"
set "LIQ_PGUSER=liq_map_user"
set "LIQ_PGPASSWORD=2848"
if exist "..\.venv\Scripts\python.exe" (set "PY=..\.venv\Scripts\python.exe") else (set "PY=python")
"%PY%" main.py
