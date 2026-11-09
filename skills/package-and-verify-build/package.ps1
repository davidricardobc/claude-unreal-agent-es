# package.ps1 | Plantilla de la skill package-and-verify-build.
# NO esta lista para correr: reemplaza los marcadores o pasa los parametros.
# Solo ASCII a proposito (PowerShell 5.1 lee mal los acentos sin BOM).
# Uso: .\package.ps1 -UERoot "<UE_ROOT>" -Proyecto "<Proyecto>" -Salida "<Salida>" [-Mapas "<MapaA>+<MapaB>"] [-Limpio] [-Hilos 4] [-DryRun]
# Verificado en la maquina real (UE 5.8.4, 8-nov-2026): todas las banderas de abajo existen y el
# build sale en <Salida>\Windows. NO agregar -SkipCookingEditorContent: rompe el cook (ExitCode=25)
# si un plugin como Landmass referencia contenido de editor.
param(
  [string]$UERoot   = "<UE_ROOT>",    # ej. C:\Program Files\Epic Games\UE_5.8
  [string]$Proyecto = "<Proyecto>",   # ruta completa del .uproject, corta y sin espacios, ej. C:\Proj\MiJuego.uproject
  [string]$Salida   = "<Salida>",     # carpeta de salida, sin espacios, ej. C:\Proj\out
  [string]$Mapas    = "",             # opcional: MapaA+MapaB. Vacio = lista de Project Settings > Packaging
  [switch]$Limpio,                    # agrega -clean (cook en frio, mas lento)
  [switch]$NoCompileEditor,           # editor abierto: no recompilar el editor (verificado 8-nov)
  [int]$Hilos       = 4,              # tope de acciones de UBT (-UbtArgs=-MaxParallelActions=N). 0 = sin tope
  [switch]$DryRun                     # solo imprime el comando, no corre UAT ni revisa rutas
)
$ErrorActionPreference = "Stop"

foreach ($v in @($UERoot, $Proyecto, $Salida)) {
  if ($v -match "[<>]") { throw "Faltan marcadores por reemplazar: $v" }
}
if ($Proyecto -match "\s" -or $Salida -match "\s") { throw "Proyecto y Salida sin espacios (ver SKILL.md, prerrequisito 3)." }

$uat = Join-Path $UERoot "Engine\Build\BatchFiles\RunUAT.bat"
if (-not $DryRun) {
  if (-not (Test-Path $uat))      { throw "No existe $uat" }
  if (-not (Test-Path $Proyecto)) { throw "No existe $Proyecto" }
  New-Item -ItemType Directory -Force $Salida | Out-Null
}
$log = Join-Path $Salida ("uat-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")

# Banderas confirmadas en ProjectParams.cs y en vivo. -compressed y -nocompileeditor no salen en -help pero existen.
$uatArgs = @(
  "BuildCookRun", "-project=$Proyecto", "-noP4", "-utf8output", "-unattended",
  "-platform=Win64", "-targetplatform=Win64", "-clientconfig=Development",
  "-build", "-cook", "-stage", "-pak", "-iostore", "-compressed", "-prereqs", "-package",
  "-archive", "-archivedirectory=$Salida"
)
if ($Mapas)  { $uatArgs += "-map=$Mapas" }
if ($Limpio) { $uatArgs += "-clean" }
if ($NoCompileEditor) { $uatArgs += "-nocompileeditor" }
# Laptop de 4 hilos: sin tope UBT satura la maquina. Verificado: 116 s el game target con 4.
if ($Hilos -gt 0) { $uatArgs += "-UbtArgs=-MaxParallelActions=$Hilos" }

if ($DryRun) {
  Write-Host ("DRYRUN $uat " + ($uatArgs -join " "))
  exit 0
}

Write-Host ("UAT empieza " + (Get-Date -Format s) + ". Log: $log")
Write-Host ("Comando: $uat " + ($uatArgs -join " "))
# Sin 2>&1: en PowerShell 5.1 convierte stderr en errores. UAT escribe lo importante por stdout.
& $uat @uatArgs | Tee-Object -FilePath $log
$code = $LASTEXITCODE
Write-Host ("UAT termino con codigo $code (" + (Get-Date -Format s) + ")")

Select-String -Path $log -Pattern "ExitCode=", "BUILD SUCCESSFUL", "BUILD FAILED", "Error:" |
  Select-Object -Last 15 | ForEach-Object { $_.Line }

if ($code -ne 0) {
  Write-Host "FALLO. Abre el log de cook que UAT imprimio, busca 'Error:' y mira la tabla de errores del SKILL.md."
  exit $code
}
Write-Host "OK. Busca el build en $Salida\Windows. Siguiente paso: verify-build.ps1"
