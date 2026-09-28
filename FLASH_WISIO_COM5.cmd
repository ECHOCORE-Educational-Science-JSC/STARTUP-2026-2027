@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0flash_wisio.ps1" -Port COM5
if errorlevel 1 pause
