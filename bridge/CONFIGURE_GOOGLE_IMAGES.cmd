@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please run setup_bridge.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" configure_google_images.py
set "config_result=%ERRORLEVEL%"
pause
exit /b %config_result%
