<#
Plantilla: corre un script de Python dentro de Unreal sin interfaz y devuelve solo lo importante.
Solo con el editor CERRADO y sin GPU: con el editor abierto no hay forma de correr Python por MCP
(execute_tool_script es un sandbox sin import unreal); usar las herramientas del MCP.

Uso:
  powershell -File run-python.ps1 -UERoot "<UE_ROOT>" -Project "<ProyectoDir>\<Proyecto>.uproject" -Script "<ruta>\x.py"
  (alternativa mas lenta, abre el editor completo: agregar -Mode ExecutePythonScript)

Convencion: el script debe imprimir la linea KIT_OK al terminar bien (print("KIT_OK")).
No hay codigo de salida fiable del commandlet, asi que el exito se decide por esa linea.
Codigos de salida: 0 ok, 1 error o sin KIT_OK, 2 editor abierto, 3 tiempo agotado,
4 aparecio KIT_OK pero el log trae Traceback o Error (NO cuenta como verde: revisar).
-ParseLog <log>: no corre Unreal, solo analiza un log (lo usan los tests).
#>
param(
  [string]$UERoot,
  [string]$Project,
  [string]$Script,
  [string]$ParseLog,
  [ValidateSet("pythonscript", "ExecutePythonScript")][string]$Mode = "pythonscript",
  [int]$TimeoutSec = 600,
  [int]$Max = 30,
  [switch]$Force
)

if ($ParseLog) {
  $log = (Resolve-Path -LiteralPath $ParseLog).Path
} else {
if (-not $UERoot -or -not $Project -or -not $Script) { Write-Output "FALTA -UERoot, -Project o -Script"; exit 5 }
$uproj = (Resolve-Path -LiteralPath $Project).Path
$py = (Resolve-Path -LiteralPath $Script).Path

if (-not $Force -and (Get-Process -Name "UnrealEditor","UnrealEditor-Cmd" -ErrorAction SilentlyContinue)) {
  Write-Output "ABORTA: hay un UnrealEditor abierto sobre algun proyecto. Cierralo o usa -Force si es otro proyecto."
  exit 2
}

$logDir = Join-Path (Split-Path $uproj) "Saved\Logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "headless-python.log"
if (Test-Path $log) { Remove-Item $log -Force }

$exe = Join-Path $UERoot "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
if ($Mode -eq "pythonscript") {
  $argList = @("`"$uproj`"", "-run=pythonscript", "-script=`"$py`"", "-unattended", "-nopause", "-stdout", "-abslog=`"$log`"")
} else {
  $argList = @("`"$uproj`"", "-ExecutePythonScript=`"$py`"", "-NullRHI", "-unattended", "-nopause", "-stdout", "-abslog=`"$log`"")
}

$p = Start-Process -FilePath $exe -ArgumentList $argList -NoNewWindow -PassThru
if (-not $p.WaitForExit($TimeoutSec * 1000)) {
  Stop-Process -Id $p.Id -Force
  Write-Output "TIMEOUT tras $TimeoutSec s. Proceso terminado. Log: $log"
  exit 3
}
}

if (-not (Test-Path $log)) { Write-Output "FAIL sin log en $log (revisar -abslog y la ruta del motor)"; exit 1 }
$lines = Get-Content $log
$hits = $lines | Where-Object { $_ -match 'Traceback|LogPython: Error|Error:|Fatal error|Ensure condition failed|Assertion failed' }
$hits | Select-Object -First $Max | ForEach-Object { Write-Output $_.Trim() }
$ok = [bool]($lines | Where-Object { $_ -match 'KIT_OK' })

if ($ok -and -not $hits) { Write-Output "PYTHON OK ($Mode)"; exit 0 }
if ($ok) { Write-Output "PYTHON AVISOS: hay KIT_OK pero tambien errores arriba. No es verde. log=$log"; exit 4 }
Write-Output "PYTHON FAIL: no aparecio KIT_OK. log=$log"
exit 1
