@echo off
setlocal
cd /d "%~dp0"
if not exist ".tmp" mkdir ".tmp"
set "TEMP=%CD%\.tmp"
set "TMP=%TEMP%"

if exist ".venv\Scripts\python.exe" goto install

set "PYTHON_EXE="
for /f "delims=" %%P in ('py -3.11 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE for /f "delims=" %%P in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE for /f "delims=" %%P in ('py -3.13 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE for /f "delims=" %%P in ('py -3.14 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"

if not defined PYTHON_EXE (
  echo Khong tim thay Python. Hay cai Python 3.11 tro len roi chay lai file nay.
  pause
  exit /b 1
)

"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,15) else 1)"
if errorlevel 1 (
  echo Can Python tu 3.11 den 3.14. Ban Python hien tai khong duoc ho tro.
  pause
  exit /b 1
)

echo Dang tao moi truong rieng cho bridge...
"%PYTHON_EXE%" -m venv .venv
if errorlevel 1 goto failed

:install
".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if errorlevel 1 (
  echo Dang hoan tat bo cai Python cuc bo...
  ".venv\Scripts\python.exe" -m ensurepip --upgrade
  if errorlevel 1 goto failed
)
echo Dang cai cac thanh phan can thiet...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" check_install.py
if errorlevel 1 goto failed
echo.
echo Cai dat bridge hoan tat. Hay nhap dup start_bridge.cmd de su dung.
pause
exit /b 0

:failed
echo.
echo Cai dat khong thanh cong. Kiem tra Internet va thu chay lai file nay.
pause
exit /b 1
