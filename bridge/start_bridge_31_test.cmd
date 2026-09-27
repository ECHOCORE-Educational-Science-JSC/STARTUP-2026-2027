@echo off
setlocal
set "GEMINI_MODEL=gemini-3.1-flash-live-preview"
echo Diagnostic test: Gemini 3.1 Flash Live (no proactive audio).
call "%~dp0start_bridge.cmd"
