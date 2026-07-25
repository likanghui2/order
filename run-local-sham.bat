@echo off
:: 1. 告诉 Windows 窗口用 UTF-8
chcp 65001

:: 2. 关键：告诉 Python 内核全面启用 UTF-8 模式
set PYTHONUTF8=1

cd /d "%~dp0"
set PYTHONPATH=%CD%;%PYTHONPATH%
set PYTHON_BIN=.venv\Scripts\python.exe

-+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
echo 正在启动本地 FastAPI 服务...
"%PYTHON_BIN%" -m uvicorn app.api:app --host 0.0.0.0 --port 8018 --reload --reload-dir app --reload-dir static --reload-dir task
pause