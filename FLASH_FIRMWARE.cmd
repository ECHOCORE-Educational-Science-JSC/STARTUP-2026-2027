@echo off
setlocal
cd /d "%~dp0"
title Wisio Firmware Flasher

set "PY="
if exist "bridge\.venv\Scripts\python.exe" set "PY=bridge\.venv\Scripts\python.exe"
if not defined PY for /f "delims=" %%P in ('where python 2^>nul') do if not defined PY set "PY=%%P"
if not defined PY for /f "delims=" %%P in ('where py 2^>nul') do if not defined PY set "PY=%%P"

if not defined PY (
    echo [!] Khong tim thay Python tren may!
    echo Vui long cai Python 3.11 hoac chay setup_bridge.cmd trong thu muc bridge truoc.
    pause
    exit /b 1
)

"%PY%" flash_firmware.py
