---
name: ue-headless
description: Trabaja con Unreal Engine 5.8 sin abrir el editor. Compila con UnrealBuildTool y devuelve solo los errores (archivo, línea, mensaje), corre scripts de Python dentro de UE sin interfaz (UnrealEditor-Cmd con -run=pythonscript, o -ExecutePythonScript) y corre pruebas automáticas con -NullRHI leyendo index.json o el log. Úsala tras editar archivos .h, .cpp o .Build.cs, para importar o crear assets por lote con Python, o antes de empaquetar. Frases disparadoras - "compila el proyecto", "build sin editor", "dame solo los errores", "corre este script de Python en Unreal", "corre las pruebas", "headless", "UBT", "compile errors", "run the automation tests", "run python in Unreal without the editor".
---

# ue-headless

Tres tareas sin editor visible: compilar, correr Python, correr pruebas. En todas: salida corta (errores, no el log entero) y nada de adivinar el éxito, porque el código de salida de UBT/Python no siempre es fiable.

## Marcadores

- `<UE_ROOT>`: raíz del motor, por ejemplo `C:\Program Files\Epic Games\UE_5.8`.
- `<ProyectoDir>`: carpeta del `.uproject`. `<Proyecto>`: nombre sin extensión. El objetivo del editor es `<Proyecto>Editor`.
- Plantillas en `.claude/skills/ue-headless/scripts/` (`build.ps1`, `run-python.ps1`, `run-tests.ps1`, `smoke_test.py`, `api_probe.py`). Se copian o se llaman desde ahí. Los scripts detectan `UnrealEditor` y `UnrealEditor-Cmd`.
- **Correr desde PowerShell**, no desde Git Bash: Git Bash convierte rutas como `/Engine/Maps/Entry` o `/Game/...` en `C:/Program Files/Git/...` (verificado: el editor abrió `/Temp/Untitled_1`). Si no hay más remedio, `MSYS_NO_PATHCONV=1`.

## Antes de empezar

1. El editor debe estar cerrado. Los tres scripts abortan si ven `UnrealEditor.exe` (se salta con `-Force`).
2. Si el editor está abierto con Live Coding y solo cambió el cuerpo de una función, usar `LiveCodingToolset.CompileLiveCoding` por MCP en vez de UBT.
3. Si hay `UFUNCTION`, `UPROPERTY` o `USTRUCT` nuevos o quitados: compilar con UBT, no con Live Coding, y avisar "cerrar y reabrir el editor".

## 1. Compilar y devolver solo errores

```
powershell -File .claude/skills/ue-headless/scripts/build.ps1 -UERoot "<UE_ROOT>" -Project "<ProyectoDir>\<Proyecto>.uproject"
```

Equivale a `"<UE_ROOT>\Engine\Build\BatchFiles\Build.bat" <Proyecto>Editor Win64 Development -Project="<ProyectoDir>\<Proyecto>.uproject" -WaitMutex -MaxParallelActions=4`. El tope de 4 acciones (`-Hilos`, 0 = sin tope) evita saturar una laptop de 4 hilos; verificado (game target 116 s, editor 109 a 136 s en frío). Si falla con `Could not find NetFxSDK install dir`, falta el .NET Framework SDK: ver `package-and-verify-build`, prerrequisito 1. El script guarda el log completo en `Saved/Logs/headless-build.log` y muestra hasta 30 errores únicos como `archivo(línea): código mensaje`, y la última línea `BUILD OK` o `BUILD FAIL`.

- Reintento acotado: máximo 3 vueltas de "corregir y compilar". Si el mismo error sigue igual, parar y mostrar el contexto a la persona.
- Si cambió un `.Build.cs` o se agregaron archivos: regenerar proyecto con `"<UE_ROOT>\Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe" -projectfiles -project="<ProyectoDir>\<Proyecto>.uproject" -game` (sin sufijo `-engine`: mete proyectos del motor; con motor instalado sobra). Alternativa: `"<UE_ROOT>\Engine\Build\BatchFiles\GenerateProjectFiles.bat" -project="..." -game`. Sin verificar en 5.8: correr con `-help` (1 minuto).
- Errores de `UnrealHeaderTool` (macros mal escritas, `GENERATED_BODY`) salen en el mismo formato.

## 2. Python dentro de UE sin interfaz

```
powershell -File .claude/skills/ue-headless/scripts/run-python.ps1 -UERoot "<UE_ROOT>" -Project "<ProyectoDir>\<Proyecto>.uproject" -Script "<ruta>\x.py"
```

Equivale a `"<UE_ROOT>\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "<Proyecto>.uproject" -run=pythonscript -script="<ruta>\x.py" -unattended -nopause -stdout -abslog="<log>"`.

- Es rápido y no abre la interfaz. No carga niveles: hay que cargarlos dentro del script. Necesita el plugin "Python Editor Script" activo.
- Alternativa más lenta (abre el editor completo): `-Mode ExecutePythonScript`, que usa `-ExecutePythonScript="x.py" -NullRHI`. Necesita también Editor Scripting Utilities. Si el editor no se cierra solo, terminar el script con `unreal.SystemLibrary.execute_console_command(None, "QUIT_EDITOR")` (sin verificar).
- Convención: el script imprime `KIT_OK` al final. El wrapper decide el éxito por esa línea, no por el código de salida. Si sale `KIT_OK` pero el log trae `Traceback` o `Error:`, el wrapper sale con 4 ("PYTHON AVISOS"): no es verde, revisar.
- Con el editor abierto no se corre Python: el wrapper aborta (código 2) y `execute_tool_script` del MCP es un sandbox sin `import unreal`. Con el editor abierto, usar las herramientas del MCP.
- Probar primero con `smoke_test.py` (solo lee: versión del motor y cantidad de assets).
- Guardar solo lo tocado (`unreal.EditorAssetLibrary.save_asset("/Game/...")`), nunca todo.
- Para escribir scripts: activar Developer Mode en Project Settings > Python. Genera `Intermediate/PythonStub/unreal.py`; buscarlo con grep, no leerlo entero.
- **Sonda de API compartida** (`api_probe.py`): lee los `api.txt` de todas las skills (o las de `KIT_API_SKILLS=a,b`) y revisa cada `Clase.miembro` en `unreal`. Con la marca `func` o `prop` revisa además si se llama con `()` o va con `get/set_editor_property`: un `hasattr` solo no caza llamar una propiedad como función (pasó con `bIsComponentPartitioned`). Formato y ejemplos en el encabezado del script. Fuera de UE solo valida el formato (`KIT_PROBE_SKIP`). Día 1: `run-python.ps1 -Script .claude/skills/ue-headless/scripts/api_probe.py`, 1 minuto.
- Data Tables desde CSV: `unreal.DataTableFunctionLibrary.fill_data_table_from_csv_file(tabla, ruta, import_row_struct)`. Vacía la tabla antes de llenarla; encabezados iguales a los nombres del struct; CSV en UTF-8 con BOM si hay tildes.

## 3. Pruebas automáticas sin render

```
powershell -File .claude/skills/ue-headless/scripts/run-tests.ps1 -UERoot "<UE_ROOT>" -Project "<ProyectoDir>\<Proyecto>.uproject" -Filter "Project"
```

Equivale a `UnrealEditor-Cmd.exe <Proyecto>.uproject -ExecCmds="Automation RunTests <Filtro>; Quit" -unattended -nopause -NullRHI -log -ReportExportPath="<ProyectoDir>\Saved\AutomationReports\headless"`.

- El log trae `**** TEST COMPLETE. EXIT CODE: N ****` (0 = sin fallas, doc de Epic). El script lee `index.json` (`state` Fail o Error cuenta como falla; `Skipped` se reporta aparte y NO es falla) y, si no existe, usa ese código del log.
- La ruta del reporte va sin barra final (un foro reporta que con barra falla).
- `-ReportExportPath` es el vigente en 5.8 (`AutomationControllerManager.cpp`); `-ReportOutputPath` es el alias viejo y avisa.
- `-NullRHI` no dibuja: las pruebas visuales necesitan GPU y se corren con el editor normal.
- Con el editor abierto, por MCP: `AutomationTestToolset.DiscoverTests` primero (si no, resultados vacíos), luego `ListTests`, `RunTests`, `GetTestStatus`, `GetTestResults`.
- 0 pruebas encontradas casi siempre es un filtro mal escrito. No se reporta como "pasó".

## Pruebas de la skill

`python -I .claude/skills/ue-headless/tests/test_headless.py` (6 pruebas) y `python -I .claude/skills/ue-headless/tests/test_api_probe.py` (8 pruebas), sin Unreal ni red. Usan `build.ps1 -ParseLog/-PrintArgs`, `run-python.ps1 -ParseLog` y `run-tests.ps1 -ParseOnly` sobre logs y un `index.json` de muestra, y la sonda con un módulo `unreal` falso (incluye el caso propiedad llamada como función). Lo que sí necesita Unreal sigue "sin verificar" abajo.

## Trampas

- UBT con el editor abierto: puede negarse o dejar binarios a medias. Cerrar el editor.
- El commandlet de Python en 5.8 activa el control de versiones antes de correr; con UEGitPlugin puede tardar o pedir algo. Si se cuelga, usar el plan B de `-ExecutePythonScript`.
- En versiones viejas hubo cierres inesperados del commandlet de Python. Siempre usar `TimeoutSec` (los scripts lo traen) y matar el proceso colgado.
- 5.8.4 arregla un atasco del log de UAT (búfer de 1.024 líneas) y la salida de commandlets con otras páginas de códigos. Antes de 5.8.4 el log de UAT puede atascarse.
- VS 2026 con 5.8.1: UBT pudo generar proyectos de VS 2022 y fallar. Revisar Editor Preferences > Source Code Editor.
- Leer logs con `grep -a`: el log puede traer bytes no UTF-8.

## Sin verificar (confirmar el día 1)

- `-WaitMutex` y el comportamiento de UBT con Live Coding activo (si se niega): `Build.bat -help`, 1 minuto.
- `-abslog=`, `-stdout`, `-nopause` en el commandlet de Python: correr `smoke_test.py` una vez y ver que el log sale en `Saved/Logs/headless-python.log`.
- Que la sonda distinga `prop` de `func` dentro de UE como en la prueba (el descriptor de una UPROPERTY no es callable): correrla una vez con `KIT_API_SKILLS=build-tile` y ver `OK` en `is_component_partitioned prop`.
- La forma exacta de `index.json` (campos `tests`, `state`, `fullTestPath`, `entries`): el script la lee con campos opcionales.
- Que `-run=pythonscript` cargue `Python Editor Script` solo si el plugin está activo en el `.uproject`.
