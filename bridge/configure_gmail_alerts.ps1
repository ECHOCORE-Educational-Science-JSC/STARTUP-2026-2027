$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host 'CAU HINH GMAIL GUI CANH BAO CHO PHU HUYNH' -ForegroundColor Cyan
Write-Host 'Can bat Xac minh 2 buoc va tao Mat khau ung dung 16 ky tu trong Tai khoan Google.'
$sender = Read-Host 'Gmail gui canh bao (vi du cp.echocore@gmail.com)'
if ($sender -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') { throw 'Dia chi Gmail khong hop le.' }
$secret = Read-Host 'Nhap Mat khau ung dung 16 ky tu' -AsSecureString
if ($secret.Length -lt 16) { throw 'Day chua phai Mat khau ung dung 16 ky tu cua Google.' }
$sender | Set-Content -LiteralPath (Join-Path $base '.wisio_alert_sender') -Encoding ASCII -NoNewline
$secret | ConvertFrom-SecureString | Set-Content -LiteralPath (Join-Path $base '.wisio_alert_secret') -Encoding ASCII -NoNewline
Write-Host 'Da luu ma hoa cho tai khoan Windows hien tai. Hay khoi dong lai start_bridge.cmd.' -ForegroundColor Green
