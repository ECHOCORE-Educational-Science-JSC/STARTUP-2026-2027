@echo off
setlocal
set "XIAOZHI_DIAGNOSTIC=1"
echo Diagnostic mode: one short mic recording is saved locally, then a speaker test is sent if needed.
call "%~dp0start_bridge.cmd"
