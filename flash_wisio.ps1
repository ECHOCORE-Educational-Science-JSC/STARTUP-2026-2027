[CmdletBinding()]
param(
    [string]$Port = "COM5",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$firmwareRoot = Join-Path $repoRoot "firmware"
$idfRoot = "C:\Espressif\frameworks\esp-idf-v5.5.3"
$idfPython = "C:\Espressif\python_env\idf5.5_py3.11_env\Scripts\python.exe"

Write-Host "Stopping ESP-IDF serial monitors that can lock $Port..." -ForegroundColor Cyan
try {
    Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object {
            $_.ProcessId -ne $PID -and $_.CommandLine -and
            ($_.CommandLine -match "idf_monitor\.py" -or
             $_.CommandLine -match "idf\.py(?:\.exe)?[^\r\n]*\bmonitor\b")
        } |
        ForEach-Object {
            Write-Host "Closing monitor process $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
        }
} catch {
    Write-Warning "Could not enumerate monitor processes. Close every ESP-IDF Monitor terminal in VS Code before retrying."
}

$ports = [System.IO.Ports.SerialPort]::GetPortNames()
if ($Port -notin $ports) {
    throw "$Port is not available. Connected ports: $($ports -join ', ')"
}
if (-not (Test-Path $idfPython)) {
    throw "ESP-IDF Python was not found at $idfPython"
}

$env:IDF_PATH = $idfRoot
$env:IDF_TOOLS_PATH = "C:\Espressif"
$env:IDF_PYTHON_ENV_PATH = "C:\Espressif\python_env\idf5.5_py3.11_env"
$env:PATH = "C:\Espressif\tools\cmake\3.30.2\bin;C:\Espressif\tools\ninja\1.12.1;" + $env:PATH

Push-Location $firmwareRoot
try {
    if (-not $SkipBuild) {
        Write-Host "Building Wisio firmware..." -ForegroundColor Cyan
        & $idfPython "$idfRoot\tools\idf.py" build
        if ($LASTEXITCODE -ne 0) { throw "Firmware build failed." }
    }

    Write-Host "Flashing $Port at a conservative baud rate..." -ForegroundColor Cyan
    # Flash only. Do not append `monitor`: a reset loop must never create more
    # serial-monitor terminals or keep the COM port locked after this command.
    & $idfPython "$idfRoot\tools\idf.py" -p $Port -b 115200 flash
    if ($LASTEXITCODE -ne 0) { throw "Firmware flash failed." }
    Write-Host "Flash completed. Unplug and reconnect the robot with a short data-capable USB cable." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "Recovery: close VS Code Monitor terminals, hold BOOT, tap RESET once, release BOOT, then run this script again." -ForegroundColor Yellow
    Write-Host "A Brownout message means the board also needs a stable 5 V source/cable; firmware cannot repair a collapsing supply." -ForegroundColor Yellow
    throw
} finally {
    Pop-Location
}
