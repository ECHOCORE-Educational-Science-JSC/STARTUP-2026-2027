@echo off
setlocal
set PORT=COM5
if not "%~1"=="" set PORT=%~1
echo ========================================================
echo   [Wisio Flash] Nap truc tiep firmware vao %PORT%...
echo ========================================================
C:\Espressif\python_env\idf5.5_py3.11_env\Scripts\python.exe C:\Espressif\frameworks\esp-idf-v5.5.3\components\esptool_py\esptool\esptool.py --chip esp32s3 -p %PORT% -b 460800 --before default_reset --after hard_reset write_flash 0x20000 "%~dp0firmware\build\xiaozhi.bin"
if errorlevel 1 (
    echo.
    echo [LOI] Khong nap duoc! Kiem tra lai cong COM hoac giu BOOT, bam RESET roi thu lai.
    echo Ban co the truyen cong COM khac: FLASH_APP_COM5.cmd COMx
    pause
) else (
    echo.
    echo [THANH CONG] Da nap xong firmware! Wisio se tu khoi dong lai.
)
