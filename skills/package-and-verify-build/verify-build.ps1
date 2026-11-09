# verify-build.ps1 | Plantilla de la skill package-and-verify-build.
# Mide el build, quita .pdb, comprime, hace smoke test y anota en docs\builds.md.
# NO esta lista para correr: reemplaza los marcadores. Solo ASCII a proposito.
# Ejecutar desde la raiz del repo (para el hash del commit y docs\builds.md).
# Uso: .\verify-build.ps1 -Staged "<Salida>\Windows" -Exe "<NombreExe>" -Zip "<TeamName>_<GameName>.zip" [-Nota "windows-test"]
param(
  [string]$Staged   = "<Salida>\Windows",
  [string]$Exe      = "<NombreExe>",                 # ej. MiJuego.exe
  [string]$Zip      = "<TeamName>_<GameName>.zip",
  [string]$Nota     = "",                            # libre: windows-test, final, etc.
  [string]$Registro = "docs\builds.md",
  [int]$EsperaSeg   = 60,
  [switch]$SinZip,
  [switch]$SinSmoke
)
$ErrorActionPreference = "Stop"
foreach ($v in @($Staged, $Exe, $Zip)) { if ($v -match "[<>]") { throw "Faltan marcadores por reemplazar: $v" } }
if (-not (Test-Path $Staged)) { throw "No existe $Staged" }
if (-not $SinZip -and $Zip -notmatch '^[A-Za-z0-9-]+_[A-Za-z0-9-]+\.zip$') {
  throw "Nombre de zip '$Zip' no cumple TeamName_GameName.zip (letras, numeros y guion; un solo guion bajo)."
}

function Tam([string]$ruta) { (Get-ChildItem $ruta -Recurse -File | Measure-Object Length -Sum).Sum }

# 1. Quitar .pdb del staged (idea de la Action de Sector9). Es una carpeta derivada, no el proyecto.
$pdbs = Get-ChildItem $Staged -Recurse -Filter *.pdb -File
if ($pdbs) { Write-Host ("Borrando " + $pdbs.Count + " archivos .pdb del staged"); $pdbs | Remove-Item -Force }

# 2. Medir el staged
$stagedGB = [math]::Round((Tam $Staged) / 1GB, 2)
Write-Host "Staged: $stagedGB GiB"

# 3. Zip con 7-Zip (no Compress-Archive). Sin carpeta raiz.
$zipRuta = Join-Path (Split-Path $Staged -Parent) $Zip
$zipGB = "n/a"; $sha = "n/a"; $limite = "n/a"
if (-not $SinZip) {
  if (Test-Path $zipRuta) { Remove-Item $zipRuta -Force }
  if (Get-Command 7z -ErrorAction SilentlyContinue) {
    & 7z a -tzip -mx=9 $zipRuta (Join-Path $Staged "*") | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "7z fallo con codigo $LASTEXITCODE" }
  } else {
    # Respaldo sin 7-Zip: .NET ZipFile (sin carpeta raiz, rutas con barra normal). Menos compresion que 7z.
    Write-Warning "7z no esta en el PATH: uso System.IO.Compression (instala 7-Zip para -mx=9)."
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory((Resolve-Path $Staged).Path, $zipRuta, [System.IO.Compression.CompressionLevel]::Optimal, $false)
  }
  $bytes = (Get-Item $zipRuta).Length
  $zipGB = [math]::Round($bytes / 1GB, 2)
  # Margen conservador: 1 GB decimal (1e9). Si pasa, usar butler (la regla lo permite).
  $limite = if ($bytes -lt 1000000000) { "OK <1 GB" } else { "PASA DE 1 GB: usar butler" }
  $sha = (Get-FileHash $zipRuta -Algorithm SHA256).Hash
  Write-Host "Zip: $zipRuta | $zipGB GiB | $limite | SHA256 $sha"
}

# 4. Smoke test: arranca, espera, revisa que siga vivo y busca Fatal error. No reemplaza la otra maquina.
$smoke = "omitido"
if (-not $SinSmoke) {
  $exePath = Join-Path $Staged $Exe
  if (-not (Test-Path $exePath)) { throw "No existe $exePath" }
  $inicio = Get-Date
  $stagedAbs = (Resolve-Path $Staged).Path.TrimEnd('\') + '\'
  # El .exe de la raiz es un lanzador: el juego real es <Proyecto>\Binaries\Win64\<Proyecto>.exe (verificado en 5.8).
  # Se mide y se mata por ruta: cualquier proceso que viva dentro del staged.
  $dentro = { @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($stagedAbs, [StringComparison]::OrdinalIgnoreCase) }) }
  $p = Start-Process $exePath -ArgumentList "-log -windowed -ResX=1280 -ResY=720" -PassThru
  Start-Sleep -Seconds $EsperaSeg
  $vivos = & $dentro
  $murio = ($vivos.Count -eq 0)
  $vivos | Stop-Process -Force -ErrorAction SilentlyContinue
  $logJuego = Get-ChildItem $Staged -Recurse -Filter *.log -File | Where-Object { $_.LastWriteTime -ge $inicio } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  $fatales = 0
  if ($logJuego) {
    $fatales = @(Select-String -Path $logJuego.FullName -Pattern "Fatal error").Count
    Write-Host ("Log del juego: " + $logJuego.FullName)
    Select-String -Path $logJuego.FullName -Pattern "Error:" | Select-Object -First 10 | ForEach-Object { $_.Line }
  } else { Write-Host "No encontre log nuevo (confirmar la ruta del log en 5.8)." }
  $smoke = if ($murio -or $fatales -gt 0) { "FALLO (cerro solo: $murio, Fatal error: $fatales)" } else { "OK ${EsperaSeg}s vivo" }
  Write-Host "Smoke test: $smoke"
}

# 5. Anotar en docs\builds.md
$commit = try { (& git rev-parse --short HEAD 2>$null) } catch { $null }
if (-not $commit) { $commit = "sin-git" }
New-Item -ItemType Directory -Force (Split-Path $Registro -Parent) | Out-Null
if (-not (Test-Path $Registro)) {
  "| Fecha | Commit | Staged GiB | Zip GiB | Limite | SHA256 | Smoke | Nota |`n|---|---|---|---|---|---|---|---|" | Set-Content $Registro -Encoding utf8
}
("| " + (Get-Date -Format "yyyy-MM-dd HH:mm") + " | $commit | $stagedGB | $zipGB | $limite | $sha | $smoke | $Nota |") | Add-Content $Registro -Encoding utf8
Write-Host "Anotado en $Registro. Falta la prueba en otra maquina (SKILL.md, paso 7)."
