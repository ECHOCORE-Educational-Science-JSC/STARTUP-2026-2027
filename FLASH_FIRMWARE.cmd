@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist "bridge\.venv\Scripts\python.exe" (
 echo Hay chay SETUP_BRIDGE.cmd truoc de cai Python va cong cu nap.
 pause
 exit /b 1
)
"bridge\.venv\Scripts\python.exe" flash_firmware.py
if errorlevel 1 pause
