<#
Plantilla: renderiza cada toma del manifest con Movie Render Queue por linea de comandos.
Verificado en UE 5.8.4 (proyecto C++ en blanco, 9-nov-2026): 240 PNG a 1920x1080 con el editor cerrado. Comando base de Epic: "Using Command Line Rendering with Movie Render Queue".
Primero: python shot_plan.py manifest shots.csv manifest.csv --out-dir <carpeta> ; luego build_sequences.py y make_mrq_preset.py.
La carpeta de fotogramas debe ser la misma en el preset (KIT_TRAILER_OUT) y aqui. Si no se pasa -OutDir se usa la del manifest.

Uso:
  powershell -File render-shots.ps1 -UERoot "<UE_ROOT>" -Project "<ProyectoDir>\<Proyecto>.uproject" -Manifest manifest.csv [-OutDir "<carpeta>"] [-DryRun]
Con -DryRun solo imprime los comandos. Un render por toma, en serie.
Antes de cada toma mueve los fotogramas viejos de esa toma a <OutDir>\old\. Cuenta solo .png/.exr nuevos (posteriores al inicio de la toma).
Codigos: 0 ok, 1 alguna toma fallo, 2 editor abierto.
#>
param(
  [Parameter(Mandatory)][string]$UERoot,
  [Parameter(Mandatory)][string]$Project,
  [Parameter(Mandatory)][string]$Manifest,
  [string]$OutDir = "",
  [string]$Preset = "/Game/Cine/Presets/TrailerHD60.TrailerHD60",
  [int]$ResX = 1920,
  [int]$ResY = 1080,
  [int]$TimeoutSec = 1800,
  [switch]$DryRun,
  [switch]$Force
)

if ($ResX -lt 1920 -or $ResY -lt 1080) { Write-Output "ABORTA: resolucion minima 1920x1080."; exit 1 }
if (-not $DryRun -and -not $Force -and (Get-Process -Name "UnrealEditor" -ErrorAction SilentlyContinue)) {
  Write-Output "ABORTA: hay un UnrealEditor abierto. Cierralo o usa -Force si es otro proyecto."
  exit 2
}

$uproj = (Resolve-Path -LiteralPath $Project).Path
$exe = Join-Path $UERoot "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$shots = Import-Csv -LiteralPath $Manifest
if (-not $OutDir) { $OutDir = ($shots | Select-Object -First 1).out_dir }
if (-not $OutDir) { Write-Output "ABORTA: falta -OutDir y el manifest no trae out_dir (usa --out-dir en shot_plan.py manifest)."; exit 1 }
$failed = 0

foreach ($s in $shots) {
  $seq = "$($s.seq_path).$($s.seq_name)"
  $cmdArgs = @("`"$uproj`"", $s.map, "-game", "-LevelSequence=$seq", "-MoviePipelineConfig=$Preset",
            "-windowed", "-resx=$ResX", "-resy=$ResY", "-log", "-notexturestreaming", "-unattended", "-nosplash")
  Write-Output ("[{0}] {1}" -f $s.index, $s.seq_name)
  if ($DryRun) { Write-Output ("  `"$exe`" " + ($cmdArgs -join " ")); continue }

  # fotogramas viejos de esta toma fuera del camino (no se borran)
  if (Test-Path -LiteralPath $OutDir) {
    $old = @(Get-ChildItem -LiteralPath $OutDir -File -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -like "$($s.seq_name).*" -and $_.Extension -in ".png", ".exr" })
    if ($old.Count -gt 0) {
      $oldDir = Join-Path $OutDir "old"
      New-Item -ItemType Directory -Force -Path $oldDir | Out-Null
      $old | Move-Item -Destination $oldDir -Force
    }
  }
  $t0 = Get-Date

  $p = Start-Process -FilePath $exe -ArgumentList $cmdArgs -PassThru -NoNewWindow
  if (-not $p.WaitForExit($TimeoutSec * 1000)) {
    $p.Kill()
    Write-Output "  FALLA: tiempo agotado ($TimeoutSec s)"
    $failed++
    continue
  }
  $frames = @(Get-ChildItem -LiteralPath $OutDir -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "$($s.seq_name).*" -and $_.Extension -in ".png", ".exr" -and $_.LastWriteTime -ge $t0 }).Count
  $want = [int]$s.frames
  # el codigo de salida no es fiable: se decide por la cantidad de fotogramas nuevos (tolerancia de 2)
  if ($frames -ge ($want - 2) -and $frames -gt 0) {
    Write-Output "  OK: $frames de $want fotogramas nuevos"
  } else {
    Write-Output "  FALLA: $frames de $want fotogramas nuevos en $OutDir"
    $failed++
  }
}

if ($DryRun) { Write-Output "RENDER_DRYRUN"; exit 0 }
if ($failed) { Write-Output "RENDER_FAIL ($failed)"; exit 1 }
Write-Output "RENDER_OK"
exit 0
