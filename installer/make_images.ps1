# 설치 마법사의 둥근 보라색 카드 이미지(밝은/어두운 테마, 화면 배율별)를 그려서 installer\ 에 저장합니다.
# 실행: powershell -ExecutionPolicy Bypass -File installer\make_images.ps1
Add-Type -AssemblyName System.Drawing
$out = Split-Path -Parent $MyInvocation.MyCommand.Path

function RoundPath([single]$x, [single]$y, [single]$w, [single]$h, [single]$r) {
    $p = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $r * 2
    $p.AddArc($x, $y, $d, $d, 180, 90); $p.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
    $p.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90); $p.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
    $p.CloseFigure(); return $p
}
function Col([string]$hex, [int]$a = 255) { $c = [System.Drawing.ColorTranslator]::FromHtml($hex); return [System.Drawing.Color]::FromArgb($a, $c.R, $c.G, $c.B) }

# 심플 마크: 살짝 기울어진 둥근 토끼 귀 두 개 + 하얀 원 + 보라색 "RH"
function DrawBunny($g, [single]$cx, [single]$cy, [single]$R, [string]$ink = "#6A58E0") {
    $white = New-Object System.Drawing.SolidBrush (Col "#FFFFFF"); $pink = New-Object System.Drawing.SolidBrush (Col "#FFC2D6")
    $inkb = New-Object System.Drawing.SolidBrush (Col $ink)
    foreach ($sx in -1, 1) {
        $st = $g.Save()
        $g.TranslateTransform($cx + $sx * 0.50 * $R, $cy - 0.78 * $R); $g.RotateTransform($sx * 14)
        $g.FillEllipse($white, -0.25 * $R, -1.0 * $R, 0.5 * $R, 1.25 * $R)
        $g.FillEllipse($pink, -0.12 * $R, -0.82 * $R, 0.24 * $R, 0.82 * $R)
        $g.Restore($st)
    }
    $g.FillEllipse($white, $cx - $R, $cy - $R * 0.78, 2 * $R, 1.84 * $R)
    $f = New-Object System.Drawing.Font "Segoe UI", (0.98 * $R), ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
    $fmt = New-Object System.Drawing.StringFormat; $fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'
    $g.DrawString("RH", $f, $inkb, (New-Object System.Drawing.RectangleF ($cx - $R), ($cy - $R * 0.78), (2 * $R), (1.84 * $R)), $fmt)
}

function NewImage([int]$w, [int]$h, [string]$bg) {
    $bmp = New-Object System.Drawing.Bitmap $w, $h, ([System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'; $g.TextRenderingHint = 'AntiAliasGridFit'; $g.InterpolationMode = 'HighQualityBicubic'
    $g.Clear((Col $bg)); return @($bmp, $g)
}

function SideImage([int]$w, [int]$h, [single]$k, [bool]$dark, [string]$path) {
    $bg = if ($dark) { "#14141F" } else { "#EEEBFA" }
    $c1 = if ($dark) { "#8B7CFF" } else { "#7C6BF2" }; $c2 = if ($dark) { "#5A4CD0" } else { "#A99BFF" }
    $bmp, $g = NewImage $w $h $bg
    $m = 10 * $k
    $card = RoundPath $m $m ($w - 2 * $m) ($h - 2 * $m) (26 * $k)
    $grad = New-Object System.Drawing.Drawing2D.LinearGradientBrush ((New-Object System.Drawing.PointF 0, 0), (New-Object System.Drawing.PointF $w, $h), (Col $c1), (Col $c2))
    $g.FillPath($grad, $card)
    $g.SetClip($card)   # 장식 원은 카드 안쪽에만
    $deco = New-Object System.Drawing.SolidBrush (Col "#FFFFFF" 28)
    $g.FillEllipse($deco, $w * 0.45, $h * 0.62, $w * 0.9, $w * 0.9); $g.FillEllipse($deco, -$w * 0.35, -$h * 0.04, $w * 0.8, $w * 0.8)
    $g.ResetClip()
    DrawBunny $g ($w / 2) ($h * 0.42) (38 * $k)
    $fmt = New-Object System.Drawing.StringFormat; $fmt.Alignment = 'Center'
    $f1 = New-Object System.Drawing.Font "Malgun Gothic", (17 * $k), ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
    $f2 = New-Object System.Drawing.Font "Malgun Gothic", (11 * $k), ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Pixel)
    $wb = New-Object System.Drawing.SolidBrush (Col "#FFFFFF"); $wb2 = New-Object System.Drawing.SolidBrush (Col "#FFFFFF" 215)
    $g.DrawString("HaruMimi", $f1, $wb, (New-Object System.Drawing.RectangleF 0, ($h * 0.64), $w, (28 * $k)), $fmt)
    $g.DrawString("by RabbitHaru", $f2, $wb2, (New-Object System.Drawing.RectangleF 0, ($h * 0.64 + 26 * $k), $w, (18 * $k)), $fmt)
    $g.DrawString("STT  ·  Translate", $f2, $wb2, (New-Object System.Drawing.RectangleF 0, ($h * 0.64 + 52 * $k), $w, (18 * $k)), $fmt)
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Bmp); $g.Dispose(); $bmp.Dispose()
}

function SmallImage([int]$w, [int]$h, [single]$k, [bool]$dark, [string]$path) {
    $bg = if ($dark) { "#14141F" } else { "#EEEBFA" }
    $c1 = if ($dark) { "#8B7CFF" } else { "#7C6BF2" }; $c2 = if ($dark) { "#5A4CD0" } else { "#A99BFF" }
    $bmp, $g = NewImage $w $h $bg
    $s = [Math]::Min($w, $h) - 8 * $k; $x = ($w - $s) / 2; $y = ($h - $s) / 2
    $card = RoundPath $x $y $s $s (14 * $k)
    $grad = New-Object System.Drawing.Drawing2D.LinearGradientBrush ((New-Object System.Drawing.PointF $x, $y), (New-Object System.Drawing.PointF ($x + $s), ($y + $s)), (Col $c1), (Col $c2))
    $g.FillPath($grad, $card)
    DrawBunny $g ($w / 2) ($h * 0.62) (9 * $k)
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Bmp); $g.Dispose(); $bmp.Dispose()
}

$sides = @(@(164, 314, 1.0, 100), @(192, 386, 1.25, 125), @(246, 459, 1.5, 150), @(328, 604, 2.0, 200))
$smalls = @(@(55, 55, 1.0, 100), @(64, 68, 1.25, 125), @(83, 80, 1.5, 150), @(110, 106, 2.0, 200))
foreach ($dark in $false, $true) {
    $t = if ($dark) { "dark" } else { "light" }
    foreach ($s in $sides) { SideImage $s[0] $s[1] $s[2] $dark (Join-Path $out ("wiz_side_{0}_{1}.bmp" -f $t, $s[3])) }
    foreach ($s in $smalls) { SmallImage $s[0] $s[1] $s[2] $dark (Join-Path $out ("wiz_small_{0}_{1}.bmp" -f $t, $s[3])) }
}
"이미지 {0}개 생성" -f (Get-ChildItem $out -Filter "wiz_*.bmp").Count

# 앱 아이콘 (.ico, PNG 내장): 둥근 보라색 타일 + 마크
$sizes = 16, 32, 48, 64, 128, 256; $pngs = @()
foreach ($n in $sizes) {
    $bmp = New-Object System.Drawing.Bitmap $n, $n, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp); $g.SmoothingMode = 'AntiAlias'; $g.TextRenderingHint = 'AntiAliasGridFit'; $g.Clear([System.Drawing.Color]::Transparent)
    $tile = RoundPath ($n * 0.03) ($n * 0.03) ($n * 0.94) ($n * 0.94) ($n * 0.24)
    $grad = New-Object System.Drawing.Drawing2D.LinearGradientBrush ((New-Object System.Drawing.PointF 0, 0), (New-Object System.Drawing.PointF $n, $n), (Col "#8B7CFF"), (Col "#5F4FD8"))
    $g.FillPath($grad, $tile)
    DrawBunny $g ($n / 2) ($n * 0.60) ($n * 0.27)
    $ms = New-Object System.IO.MemoryStream; $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png); $pngs += , $ms.ToArray()
    $g.Dispose(); $bmp.Dispose()
    if ($n -eq 256) { [IO.File]::WriteAllBytes((Join-Path $out "icon_preview.png"), $pngs[-1]) }
}
$fs = [IO.File]::Create((Join-Path $out "HaruMimi.ico")); $bw = New-Object IO.BinaryWriter $fs
$bw.Write([uint16]0); $bw.Write([uint16]1); $bw.Write([uint16]$sizes.Count)
$off = 6 + 16 * $sizes.Count
for ($i = 0; $i -lt $sizes.Count; $i++) {
    $n = $sizes[$i]; $d = if ($n -ge 256) { 0 } else { $n }
    $bw.Write([byte]$d); $bw.Write([byte]$d); $bw.Write([byte]0); $bw.Write([byte]0); $bw.Write([uint16]1); $bw.Write([uint16]32)
    $bw.Write([uint32]$pngs[$i].Length); $bw.Write([uint32]$off); $off += $pngs[$i].Length
}
foreach ($p in $pngs) { $bw.Write($p) }
$bw.Close(); $fs.Close()
"아이콘 생성: HaruMimi.ico"
