Add-Type -AssemblyName System.Drawing
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bitmap = New-Object System.Drawing.Bitmap(320, 240)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::SingleBitPerPixelGridFit
$art = [System.Drawing.Image]::FromFile((Join-Path $root 'main/echocore_loading_bg.png'))
$white = [System.Drawing.Brushes]::White
$cyan = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(128, 243, 237))
$dark = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(28, 71, 107))
$fill = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(50, 227, 242))
$border = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(125, 234, 251), 1)
$fonts = New-Object System.Drawing.Text.PrivateFontCollection
$fonts.AddFontFile((Join-Path $root 'managed_components/lvgl__lvgl/scripts/built_in_font/Montserrat-Medium.ttf'))
$font = New-Object System.Drawing.Font($fonts.Families[0], 11, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
$small = New-Object System.Drawing.Font($fonts.Families[0], 9, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
foreach ($percent in @(42, 100)) {
    $graphics.DrawImage($art, 0, 0, 320, 240)
    $graphics.DrawString('LOADING...', $font, $white, 12, 179)
    $progressLabel = "$percent%"
    $labelWidth = $graphics.MeasureString($progressLabel, $font).Width
    $graphics.DrawString($progressLabel, $font, $white, (306 - $labelWidth), 179)
    $graphics.FillRectangle([System.Drawing.Brushes]::MidnightBlue, 10, 199, 300, 22)
    $graphics.FillEllipse([System.Drawing.Brushes]::MidnightBlue, 10, 199, 22, 22)
    $graphics.FillEllipse([System.Drawing.Brushes]::MidnightBlue, 288, 199, 22, 22)
    $graphics.DrawArc($border, 10, 199, 22, 22, 90, 180)
    $graphics.DrawArc($border, 288, 199, 22, 22, 270, 180)
    $graphics.DrawLine($border, 21, 199, 298, 199)
    $graphics.DrawLine($border, 21, 220, 298, 220)
    $fillWidth = [int][Math]::Round(292 * $percent / 100)
    $graphics.FillRectangle($fill, 21, 203, ($fillWidth - 14), 14)
    $graphics.FillEllipse($fill, 14, 203, 14, 14)
    $graphics.FillEllipse($fill, (14 + $fillWidth - 14), 203, 14, 14)
    $output = if ($percent -eq 100) { 'loading_100_preview.png' } else { 'loading_preview_final.png' }
    $bitmap.Save((Join-Path $root $output), [System.Drawing.Imaging.ImageFormat]::Png)
}
$graphics.Clear([System.Drawing.Color]::Black)
$fonts.AddFontFile((Join-Path $root 'managed_components/lvgl__lvgl/scripts/built_in_font/unscii-8.ttf'))
$pixel = New-Object System.Drawing.Font($fonts.Families[1], 16, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
$startupLabel = 'STARTING UP...'
$startupWidth = $graphics.MeasureString($startupLabel, $pixel).Width
$graphics.DrawString($startupLabel, $pixel, $white, ((320 - $startupWidth) / 2 - 9), 108)
$bitmap.Save((Join-Path $root 'startup_preview_final.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$pixel.Dispose(); $small.Dispose(); $font.Dispose(); $fonts.Dispose()
$border.Dispose(); $fill.Dispose(); $dark.Dispose(); $cyan.Dispose()
$art.Dispose(); $graphics.Dispose(); $bitmap.Dispose()
