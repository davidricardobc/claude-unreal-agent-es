# project-map.ps1 | Mapa corto de un proyecto de Unreal (paso 6 de ue-session-preflight). SOLO LEE.
# Uso: powershell -File project-map.ps1 [-ProjectDir <carpeta del .uproject>] [-MaxLines 25]
# Sale: maximo -MaxLines lineas. Exit 0 ok, 2 si no hay .uproject. Solo ASCII a proposito (PowerShell 5.1).
param([string]$ProjectDir = (Get-Location).Path, [int]$MaxLines = 25)
$ErrorActionPreference = "Stop"
$dir = (Resolve-Path -LiteralPath $ProjectDir).Path
$up = Get-ChildItem -LiteralPath $dir -Filter *.uproject -File | Select-Object -First 1
if (-not $up) { Write-Output "SIN .uproject en $dir"; exit 2 }
$out = New-Object System.Collections.Generic.List[string]
$j = Get-Content -LiteralPath $up.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
$name = [IO.Path]::GetFileNameWithoutExtension($up.Name)
$out.Add("Proyecto : $name  EngineAssociation=$($j.EngineAssociation)")
$mods = @($j.Modules | ForEach-Object { "$($_.Name)($($_.Type))" })
$out.Add("Modulos  : " + $(if ($mods.Count) { $mods -join ", " } else { "ninguno (proyecto solo de contenido)" }))
$plugs = @($j.Plugins | Where-Object { $_.Enabled } | ForEach-Object { $_.Name })
$out.Add("Plugins  : " + $(if ($plugs.Count) { ($plugs | Select-Object -First 12) -join ", " + $(if ($plugs.Count -gt 12) { " (+$($plugs.Count - 12))" } else { "" }) } else { "ninguno en el .uproject" }))

$skip = '[\\/](?:Intermediate|Saved|Binaries|DerivedDataCache|\.git)[\\/]'
$content = Join-Path $dir "Content"
$maps = @(); $dts = @()
if (Test-Path $content) {
  $maps = @(Get-ChildItem $content -Recurse -File -Filter *.umap | Where-Object { $_.FullName -notmatch $skip })
  $dts = @(Get-ChildItem $content -Recurse -File -Filter DT_*.uasset | Where-Object { $_.FullName -notmatch $skip })
}
$out.Add("Mapas    : $($maps.Count)  " + (($maps | Select-Object -First 6 | ForEach-Object { $_.BaseName }) -join ", "))
$out.Add("DataTabl : $($dts.Count)  " + (($dts | Select-Object -First 8 | ForEach-Object { $_.BaseName }) -join ", "))

$src = Join-Path $dir "Source"
$classes = New-Object System.Collections.Generic.List[string]
if (Test-Path $src) {
  foreach ($h in (Get-ChildItem $src -Recurse -File -Filter *.h)) {
    $lines = Get-Content -LiteralPath $h.FullName
    for ($i = 0; $i -lt $lines.Count; $i++) {
      if ($lines[$i] -match '^\s*(UCLASS|USTRUCT|UENUM)\b') {
        $kw = $Matches[1]
        for ($k = $i + 1; $k -lt [Math]::Min($i + 6, $lines.Count); $k++) {
          if ($lines[$k] -match '^\s*(?:class|struct|enum(?:\s+class)?)\s+(?:\w+_API\s+)?(\w+)') { $classes.Add("$kw $($Matches[1])"); break }
        }
      }
    }
  }
}
$out.Add("Clases C++: $($classes.Count)")
foreach ($c in ($classes | Select-Object -First 8)) { $out.Add("  $c") }
if ($classes.Count -gt 8) { $out.Add("  ... y $($classes.Count - 8) mas") }

$log = Join-Path $dir "Saved\Logs\$name.log"
if (Test-Path $log) {
  # abrir compartido: el editor puede tenerlo abierto
  $fs = [IO.File]::Open($log, 'Open', 'Read', 'ReadWrite'); $sr = New-Object IO.StreamReader($fs)
  $txt = $sr.ReadToEnd(); $sr.Close(); $fs.Close()
  $errs = @($txt -split "`r?`n" | Where-Object { $_ -match 'Error:|Fatal|Ensure condition failed|LogPython: Error|LogCompile.*error' })
  $out.Add("Log      : $($errs.Count) lineas de error")
  foreach ($e in ($errs | Select-Object -Last 3)) { $t = $e.Trim(); if ($t.Length -gt 140) { $t = $t.Substring(0, 140) }; $out.Add("  $t") }
} else { $out.Add("Log      : sin Saved\Logs\$name.log (el editor no ha corrido aqui)") }

$out | Select-Object -First $MaxLines | ForEach-Object { Write-Output $_ }
