@echo off
cd /d "%~dp0"

:: 优先调用 vbs 做到 100% 纯净静默无黑框
if exist "%~dp0start.vbs" (
    start "" wscript //nologo "%~dp0start.vbs"
    exit
)

:: 备用调用系统 pythonw (GUI 静默模式)
set PYTHONW_EXE=
if exist "E:\AI\venv\Scripts\pythonw.exe" set PYTHONW_EXE=E:\AI\venv\Scripts\pythonw.exe
if not defined PYTHONW_EXE if exist "venv\Scripts\pythonw.exe" set PYTHONW_EXE=venv\Scripts\pythonw.exe
if not defined PYTHONW_EXE (
    where pythonw.exe >nul 2>nul && set PYTHONW_EXE=pythonw.exe
)

if defined PYTHONW_EXE (
    start "" "%PYTHONW_EXE%" main.py
    exit
)

echo [ERROR] 未检测到 Python 运行环境！请先安装 Python 3.10 及以上版本。
pause
exit /b 1
