<#
Plantilla: corre pruebas automaticas de Unreal sin render (-NullRHI) y dice que prueba paso o fallo.
No se ejecuto contra UE 5.8 todavia. El nombre del flag del reporte esta sin confirmar:
  -ReportExportPath es el vigente en 5.8 (AutomationControllerManager.cpp); -ReportOutputPath es el alias viejo.

Uso:
  powershell -File run-tests.ps1 -UERoot "<UE_ROOT>" -Project "<ProyectoDir>\<Proyecto>.uproject" -Filter "Project.Vuelo"
  -Filter es el filtro de "Automation RunTests <Filtro>" (por ejemplo "Project" corre todas las del proyecto).

Resultado: se lee index.json; si no existe, el log. El log trae "**** TEST COMPLETE. EXIT CODE: N ****" (0 = sin fallas, doc de Epic).
-ParseOnly <carpeta del informe> [-LogFile <log>]: no lanza Unreal, solo analiza un informe ya hecho (lo usan los tests).
Codigos de salida: 0 todas pasan, 1 hay fallas, 2 editor abierto, 3 no hubo informe ni log util, 4 tiempo agotado.
Con -NullRHI no hay render: las pruebas visuales necesitan GPU y se corren aparte.
#>
param(
  [string]$UERoot,
  [string]$Project,
  [string]$Filter,
  [string]$ParseOnly,
  [string]$LogFile,
  [string]$ReportFlag = "ReportExportPath",
  [int]$TimeoutSec = 900,
  [int]$Max = 30,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
if ($ParseOnly) {
  $report = (Resolve-Path -LiteralPath $ParseOnly).Path
  $log = $LogFile
} else {
  foreach ($n in "UERoot","Project","Filter") { if (-not (Get-Variable $n -ValueOnly)) { Write-Output "FALTA parametro -$n"; exit 5 } }
  $uproj = (Resolve-Path -LiteralPath $Project).Path
  if (-not $Force -and (Get-Process -Name "UnrealEditor","UnrealEditor-Cmd" -ErrorAction SilentlyContinue)) {
    Write-Output "ABORTA: hay un UnrealEditor abierto. Cierralo o usa -Force."
    exit 2
  }

  $root = Split-Path $uproj
  $report = Join-Path $root "Saved\AutomationReports\headless"   # sin barra final: con barra final falla segun un foro
  $log = Join-Path $root "Saved\Logs\headless-tests.log"
  New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
  if (Test-Path $report) { Remove-Item $report -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $report | Out-Null
  if (Test-Path $log) { Remove-Item $log -Force }

  $exe = Join-Path $UERoot "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
  $argList = @(
    "`"$uproj`"",
    "-ExecCmds=`"Automation RunTests $Filter; Quit`"",
    "-unattended", "-nopause", "-NullRHI", "-log",
    "-$ReportFlag=`"$report`"",
    "-abslog=`"$log`""
  )
  $p = Start-Process -FilePath $exe -ArgumentList $argList -NoNewWindow -PassThru
  if (-not $p.WaitForExit($TimeoutSec * 1000)) {
    Stop-Process -Id $p.Id -Force
    Write-Output "TIMEOUT tras $TimeoutSec s. Proceso terminado. Log: $log"
    exit 4
  }

}

$index = Join-Path $report "index.json"
if (Test-Path $index) {
  $j = Get-Content $index -Raw -Encoding UTF8 | ConvertFrom-Json
  $tests = @($j.tests)
  $okStates = @("Success","Skipped","NotRun","InProcess")
  $bad = @($tests | Where-Object { $_.state -and $_.state -notin $okStates })
  $skipped = @($tests | Where-Object { $_.state -eq "Skipped" })
  $bad | Select-Object -First $Max | ForEach-Object {
    $n = if ($_.fullTestPath) { $_.fullTestPath } else { $_.testDisplayName }
    Write-Output ("FALLA {0} [{1}]" -f $n, $_.state)
    @($_.entries) | Where-Object { $_.event -and $_.event.type -eq "Error" } | Select-Object -First 3 |
      ForEach-Object { Write-Output ("   " + $_.event.message) }
  }
  Write-Output ("PRUEBAS total={0} falladas={1} saltadas={2} informe={3}" -f $tests.Count, $bad.Count, $skipped.Count, $index)
  if ($tests.Count -eq 0) { Write-Output "AVISO: 0 pruebas. Filtro vacio o falta DiscoverTests (por MCP)."; exit 3 }
  if ($bad.Count -gt 0) { exit 1 } else { exit 0 }
}

# Sin index.json: caer al log. Primero el codigo oficial del log.
if (-not $log -or -not (Test-Path $log)) { Write-Output "SIN INFORME NI LOG. Revisar rutas y flags."; exit 3 }
$logLines = Get-Content $log
$codeLine = $logLines | Where-Object { $_ -match 'TEST COMPLETE\. EXIT CODE:\s*(-?\d+)' } | Select-Object -Last 1
if ($codeLine -match 'EXIT CODE:\s*(-?\d+)') {
  $c = [int]$Matches[1]
  Write-Output "LOG: TEST COMPLETE EXIT CODE: $c (0 = sin fallas)"
  if ($c -eq 0) { exit 0 } else { exit 1 }
}
$fails = $logLines | Where-Object { $_ -match 'LogAutomationController.*(Fail|Error)|Result=\{Fail\}' }
$fails | Select-Object -First $Max | ForEach-Object { Write-Output $_.Trim() }
Write-Output "SIN index.json ni linea TEST COMPLETE (flag de reporte no reconocido?). Fallas en log: $(@($fails).Count). log=$log"
if (@($fails).Count -gt 0) { exit 1 } else { exit 3 }
