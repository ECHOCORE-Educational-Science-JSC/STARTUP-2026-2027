@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call setup_bridge.cmd
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" bridge.py
if errorlevel 1 pause
