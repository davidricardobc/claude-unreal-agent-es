# butler-push.ps1 | Plantilla de la skill package-and-verify-build.
# Subir a itch es PUBLICAR. Por defecto SOLO hace --dry-run.
# OJO: butler NO conserva el nombre del zip (itch genera el archivo de descarga). El zip TeamName_GameName.zip de un concurso se sube a mano por el formulario web.
# El push real exige -Real y -ConfirmadoPor con el si explicito de la persona autorizada en el chat (su nombre va en -ConfirmadoPor).
# No toca BUTLER_API_KEY ni lee credenciales: el "butler login" lo hace un humano.
# NO esta lista para correr: reemplaza los marcadores. Solo ASCII a proposito.
# Ejemplos:
#   .\butler-push.ps1 -Origen "<Salida>\Windows" -Destino "<usuario>/<juego>:windows-test"
#   .\butler-push.ps1 -Origen "<TeamName>_<GameName>.zip" -Destino "<usuario>/<juego>:windows" -ComoZip -Version "<version>" -Real -ConfirmadoPor "Nombre"
param(
  [Parameter(Mandatory)][string]$Origen,    # carpeta del build o zip
  [Parameter(Mandatory)][string]$Destino,   # <usuario>/<juego>:<canal>, todo en minusculas
  [string]$Version = "",                    # --userversion
  [switch]$ComoZip,                         # sube el zip tal cual (--no-auto-unzip). SIN VERIFICAR: confirmar con "butler push --help"
  [switch]$Real,
  [string]$ConfirmadoPor                    # nombre de quien dio el si; obligatorio con -Real
)
$ErrorActionPreference = "Stop"
if ($Origen -match "[<>]" -or $Destino -match "[<>]") { throw "Faltan marcadores por reemplazar." }
if ($Destino -cmatch "[A-Z]") { throw "Usuario, juego y canal van en minusculas: $Destino" }
if ($Destino -notmatch "^[a-z0-9_-]+/[a-z0-9_-]+:[a-z0-9_-]+$") { throw "Destino con forma <usuario>/<juego>:<canal>" }
if (-not (Test-Path $Origen)) { throw "No existe $Origen" }
if ($Real -and -not $ConfirmadoPor) { throw "Push real sin -ConfirmadoPor (nombre de quien dio el si). Es publicar; pide el si." }

$extra = @()
if ($Version) { $extra += @("--userversion", $Version) }
if ($ComoZip) { $extra += "--no-auto-unzip" } else { $extra += @("--ignore", "*.pdb") }

Write-Host "1/2 dry-run (no sube nada)"
& butler push --dry-run $Origen $Destino @extra
if ($LASTEXITCODE -ne 0) { throw "dry-run fallo con codigo $LASTEXITCODE" }

if (-not $Real) { Write-Host "Solo dry-run. Para subir de verdad: -Real -ConfirmadoPor <nombre>"; exit 0 }

Write-Host "2/2 push REAL confirmado por $ConfirmadoPor a $Destino"
& butler push $Origen $Destino @extra
if ($LASTEXITCODE -ne 0) { throw "push fallo con codigo $LASTEXITCODE" }
Write-Host "Subido. Verifica en la pagina de itch las etiquetas de plataforma y que siga en borrador o restringida."
