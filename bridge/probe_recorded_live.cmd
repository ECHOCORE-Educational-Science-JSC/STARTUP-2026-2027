@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call setup_bridge.cmd
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" probe_recorded_live.py
pause
