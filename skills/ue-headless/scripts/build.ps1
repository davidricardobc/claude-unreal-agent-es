<#
Plantilla: compila el proyecto con UBT sin abrir el editor y devuelve solo los errores.
Build.bat con -MaxParallelActions=4 verificado en la maquina de prueba (laptop, GTX 1660 Ti) (UE 5.8.4, 8-nov-2026).

Uso:
  powershell -File build.ps1 -UERoot "<UE_ROOT>" -Project "<ProyectoDir>\<Proyecto>.uproject"
Salida: lineas "archivo(linea): codigo mensaje", maximo -Max, y una linea final BUILD OK o BUILD FAIL.
-ParseLog <log>: no compila, solo analiza un log ya hecho (lo usan los tests).
-Hilos N: tope de acciones de UBT (-MaxParallelActions=N, 4 por defecto; 0 = sin tope).
-PrintArgs: imprime los argumentos de Build.bat y sale (lo usan los tests).
Codigos de salida: 0 ok, 1 fallo de compilacion, 2 editor abierto (no compila).
#>
param(
  [string]$UERoot,
  [string]$Project,
  [string]$ParseLog,
  [string]$Target,
  [string]$Config = "Development",
  [int]$Max = 30,
  [int]$Hilos = 4,
  [switch]$PrintArgs,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
if ($ParseLog) {
  $log = (Resolve-Path -LiteralPath $ParseLog).Path; $code = 0; $Target = "(log)"
} else {
  if (-not $UERoot -or -not $Project) { Write-Output "FALTA -UERoot o -Project"; exit 5 }
  if ($PrintArgs) {
    $name = [IO.Path]::GetFileNameWithoutExtension($Project)
    if (-not $Target) { $Target = "${name}Editor" }
    $a = @($Target, "Win64", $Config, "-Project=`"$Project`"", "-WaitMutex")
    if ($Hilos -gt 0) { $a += "-MaxParallelActions=$Hilos" }
    Write-Output ("ARGS " + ($a -join " ")); exit 0
  }
  $uproj = (Resolve-Path -LiteralPath $Project).Path
  $name = [IO.Path]::GetFileNameWithoutExtension($uproj)
  if (-not $Target) { $Target = "${name}Editor" }

  # Con el editor abierto (sobre todo con Live Coding) UBT puede negarse o dejar binarios a medias.
  if (-not $Force -and (Get-Process -Name "UnrealEditor","UnrealEditor-Cmd" -ErrorAction SilentlyContinue)) {
    Write-Output "ABORTA: hay un UnrealEditor abierto. Cierralo, o usa LiveCodingToolset.CompileLiveCoding por MCP (solo cuerpos de funciones)."
    exit 2
  }

  $logDir = Join-Path (Split-Path $uproj) "Saved\Logs"
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null
  $log = Join-Path $logDir "headless-build.log"
  $err = "$log.err"

  $bat = Join-Path $UERoot "Engine\Build\BatchFiles\Build.bat"
  $argList = @($Target, "Win64", $Config, "-Project=`"$uproj`"", "-WaitMutex")
  if ($Hilos -gt 0) { $argList += "-MaxParallelActions=$Hilos" }
  $p = Start-Process -FilePath $bat -ArgumentList $argList -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput $log -RedirectStandardError $err
  $code = $p.ExitCode
  if (Test-Path $err) { Get-Content $err | Add-Content $log; Remove-Item $err -Force }

}

# C++ (MSVC) y UHT: C:\ruta\Archivo.cpp(123): error C2065: mensaje
$rxFile = '^\s*(?<f>.+?)\((?<l>\d+)(?:,\d+)?\)\s*:\s*(?:fatal\s+)?error\s*(?<c>[A-Za-z]*\d*)\s*:?\s*(?<m>.*)$'
# Enlace y otros: Algo.obj : error LNK2019: ...   |   ERROR: ...
$rxOther = '(\berror\s+(LNK|MSB|C)\d+|^\s*ERROR:|\bFatal error\b)'

$seen = New-Object System.Collections.Generic.HashSet[string]
$out = New-Object System.Collections.Generic.List[string]
foreach ($line in (Get-Content $log)) {
  $msg = $null
  if ($line -match $rxFile) {
    $msg = "{0}({1}): {2} {3}" -f $Matches.f.Trim(), $Matches.l, $Matches.c, $Matches.m.Trim()
  } elseif ($line -match $rxOther) {
    $msg = $line.Trim()
    if ($msg.Length -gt 220) { $msg = $msg.Substring(0, 220) }
  }
  if ($msg -and $seen.Add($msg)) { $out.Add($msg) }
}

$out | Select-Object -First $Max | ForEach-Object { Write-Output $_ }
if ($out.Count -gt $Max) { Write-Output ("... y {0} errores mas (ver {1})" -f ($out.Count - $Max), $log) }

if ($code -eq 0 -and $out.Count -eq 0) {
  Write-Output "BUILD OK ($Target $Config)"
  exit 0
}
Write-Output "BUILD FAIL exit=$code errores=$($out.Count) log=$log"
exit 1
