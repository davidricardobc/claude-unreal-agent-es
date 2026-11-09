<#
Plantilla: reduce capturas y las junta en una sola imagen (montaje) para gastar menos tokens de vision.
Usa System.Drawing (Windows PowerShell 5.1, sin instalar nada). Solo lee las capturas y escribe un JPEG nuevo.

Uso (4 angulos en una rejilla de 2 columnas, 640 px de ancho por celda):
  powershell -File shrink-montage.ps1 -Images front.png,tq.png,side.png,top.png -OutFile montage.jpg
Antes y despues (2 imagenes, una al lado de la otra):
  powershell -File shrink-montage.ps1 -Images antes.jpg,despues.jpg -OutFile cmp.jpg -Columns 2 -Labels antes,despues

Costo aproximado de una imagen para Claude: ancho x alto / 750 tokens. Un montaje de 4 capturas 16:9 de 1280x720 son unos 1.230 tokens.
#>
param(
  [Parameter(Mandatory)][string[]]$Images,
  [Parameter(Mandatory)][string]$OutFile,
  [int]$Cell = 640,
  [int]$Columns = 2,
  [int]$Quality = 70,
  [string[]]$Labels
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

# Con "powershell -File" una lista con comas llega como una sola cadena: se parte aqui.
$Images = @($Images | ForEach-Object { $_ -split ',' } | Where-Object { $_ })
if ($Labels) { $Labels = @($Labels | ForEach-Object { $_ -split ',' } | Where-Object { $_ }) }
if ($Images.Count -eq 0) { [Console]::Error.WriteLine("ERROR: no se pasaron imagenes (-Images)."); exit 2 }
foreach ($i in $Images) {
  if (-not (Test-Path -LiteralPath $i -PathType Leaf)) { [Console]::Error.WriteLine("ERROR: FALTA la imagen: $i"); exit 1 }
}
$paths = $Images | ForEach-Object { (Resolve-Path -LiteralPath $_).Path }
$n = $paths.Count
$cols = [Math]::Min($Columns, $n)
$rows = [Math]::Ceiling($n / $cols)
# Celda con la proporcion de la primera imagen (16:9 no desperdicia espacio).
$bmp = $null; $g = $null; $font = $null
try {
  $first = [System.Drawing.Image]::FromFile($paths[0])
  $CellH = [int][Math]::Round($Cell * $first.Height / $first.Width)
  $first.Dispose()
  $bmp = New-Object System.Drawing.Bitmap ($cols * $Cell), ($rows * $CellH)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.Clear([System.Drawing.Color]::Black)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $font = New-Object System.Drawing.Font("Arial", 18, [System.Drawing.FontStyle]::Bold)
  $white = [System.Drawing.Brushes]::White
  $shadow = [System.Drawing.Brushes]::Black

  for ($i = 0; $i -lt $n; $i++) {
    $img = [System.Drawing.Image]::FromFile($paths[$i])
    $scale = [Math]::Min($Cell / $img.Width, $CellH / $img.Height)
    $w = [int]($img.Width * $scale); $h = [int]($img.Height * $scale)
    $x = ($i % $cols) * $Cell + [int](($Cell - $w) / 2)
    $y = [Math]::Floor($i / $cols) * $CellH + [int](($CellH - $h) / 2)
    $g.DrawImage($img, $x, $y, $w, $h)
    $label = if ($Labels -and $i -lt $Labels.Count) { $Labels[$i] } else { [IO.Path]::GetFileNameWithoutExtension($paths[$i]) }
    $g.DrawString($label, $font, $shadow, ($x + 9), ($y + 7))
    $g.DrawString($label, $font, $white, ($x + 8), ($y + 6))
    $img.Dispose()
  }
  $g.Dispose()

  $codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq "image/jpeg" }
  $ep = New-Object System.Drawing.Imaging.EncoderParameters 1
  $ep.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter ([System.Drawing.Imaging.Encoder]::Quality), ([long]$Quality)
  $outFull = [IO.Path]::GetFullPath($OutFile)
  New-Item -ItemType Directory -Force -Path (Split-Path $outFull) | Out-Null
  $bmp.Save($outFull, $codec, $ep)
  $bmp.Dispose()
} catch {
  [Console]::Error.WriteLine("ERROR al armar el montaje: " + $_.Exception.Message)
  exit 1
} finally {
  if ($g) { $g.Dispose() }
  if ($bmp) { $bmp.Dispose() }
  if ($font) { $font.Dispose() }
}

$kb = [Math]::Round((Get-Item $outFull).Length / 1024)
Write-Output ("MONTAJE {0}x{1} px, {2} KB, ~{3} tokens: {4}" -f ($cols * $Cell), ($rows * $CellH), $kb, [int](($cols * $Cell) * ($rows * $CellH) / 750), $outFull)
