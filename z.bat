@echo off
:: 1. 告诉 Windows 窗口用 UTF-8，防止控制台打印中文乱码
chcp 65001 >nul

:: 2. 关键：告诉 Python 内核全面启用 UTF-8 模式
set PYTHONUTF8=1

:: 3. 切换到当前批处理文件所在的目录（项目根目录）
cd /d "%~dp0"

:: 4. 将当前目录加入 Python 环境变量，确保 tools 内部 import 根目录模块时不报错
set PYTHONPATH=%CD%;%PYTHONPATH%

:: 5. 指定当前项目下的虚拟环境 Python 路径
set PYTHON_BIN=.venv\Scripts\python.exe

:: 安全检查：确保虚拟环境存在
if not exist "%PYTHON_BIN%" (
    echo 【错误】未在当前目录下找到虚拟环境 %PYTHON_BIN%
    echo 请确认此 .bat 文件放置在项目的根目录下（与 .venv 同级）。
    echo.
    pause
    exit /b
)

echo ===================================================
echo   [VJ_WARMER] 正在启动 越捷航空设备ID缓存预热工具...
echo ===================================================
echo 脚本路径: tools/vj_device_id_cache_warmer.py
echo 环境路径: %PYTHON_BIN%
echo ---------------------------------------------------
echo.

:: 6. 精准运行 tools 目录下的预热脚本
"%PYTHON_BIN%" tools/vj_device_id_cache_warmer.py

echo.
echo ---------------------------------------------------
echo [SYSTEM] 脚本执行完毕。
echo ===================================================
pause