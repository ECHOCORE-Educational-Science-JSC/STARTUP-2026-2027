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
".venv\Scripts\python.exe" check_google_images.py
set "check_result=%ERRORLEVEL%"
if "%check_result%"=="0" if exist "test-tmp\google-image-preview.png" echo Preview: %CD%\test-tmp\google-image-preview.png
pause
exit /b %check_result%
