---
name: ue-session-preflight
description: Deja lista una sesión de Claude Code en un proyecto de Unreal Engine 5.8 antes de tocar nada. Comprueba que el editor y el MCP de Epic responden con una llamada de lectura real, la versión 5.8.x, git limpio, bloqueos de git lfs y dueño por carpeta, crea un respaldo y carga un mapa corto del proyecto (mapas, clases C++, Data Tables, errores del log). Úsala al abrir sesión en un repo con .uproject o antes de una edición masiva. Frases disparadoras - "prepara la sesión", "preflight", "revisa que el editor esté listo", "antes de editar por MCP", "arranca el proyecto Unreal", "session preflight", "check the editor and MCP", "get me oriented in this UE project", "before bulk edit".
---

# ue-session-preflight

Evita arrancar en frío. Solo lee, salvo el respaldo de git, que se hace con el sí de quien lleva la sesión. No arregla nada: reporta con semáforo y pregunta.

## Cuándo usarla

- Al abrir sesión en un repo que tiene un `.uproject`.
- Antes de una edición masiva (más de unos 5 assets, o cualquier borrado o renombrado).
- Después de reiniciar el editor, compilar C++ o si el MCP deja de responder.

## Instalación de una sola vez (por máquina)

1. Plugin de Epic para Claude Code (trae las skills `unreal-mcp`, `create-toolset`, `unreal-skill` y un hook SessionStart):
   `/plugin install unreal-engine-skills-for-claude-code@claude-plugins-official`
2. En el proyecto, activar los plugins `ModelContextProtocol` y `AllToolsets` (Edit > Plugins) y reiniciar el editor.
3. Con el editor abierto, en su consola: `ModelContextProtocol.GenerateClientConfig ClaudeCode`. Escribe `.mcp.json` junto al `.uproject` (motor instalado) o junto a la carpeta `Engine/` (motor compilado). No sobrescribe uno existente: fusionar a mano.
4. En 5.8 el servidor no arranca solo. Elegir una (la 1 es la más segura): (1) Editor Preferences, sección del plugin Model Context Protocol, marcar auto start; (2) `Saved/Config/WindowsEditor/EditorPerProjectUserSettings.ini`, sección `[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]`, claves `bAutoStartServer=True` y `ServerPortNumber=8000` (clase `UModelContextProtocolSettings`, confirmada en la doc de Epic el 8-nov); (3) `ModelContextProtocol.StartServer` en la consola del editor; (4) los flags `-ModelContextProtocolStartServer -ModelContextProtocolPort=N` (confirmados en `ModelContextProtocolSettings.cpp` y en la máquina; en commandlets el auto start del `.ini` se ignora y solo arranca con el flag).
   Sin ventana (verificado, listo en ~45 s): `UnrealEditor.exe <proj> -ModelContextProtocolStartServer -ModelContextProtocolPort=8123 -unattended -nosplash -nullrhi`. Con `-nullrhi` no hay capturas. Lanzarlo desde PowerShell: Git Bash convierte `/Engine/...` y `/Game/...` en `C:/Program Files/Git/...` (o usar `MSYS_NO_PATHCONV=1`). Para cerrarlo: `taskkill /F /PID <pid>` del proceso propio (sin ventana no recibe el cierre normal).
5. Un puerto fijo por proyecto si hay más de un editor en la misma máquina: `ServerPortNumber=N` en el `.ini` (o el flag) y el mismo puerto en `.mcp.json`. Por defecto es el 8000.

## Pasos

1. **Identificar el proyecto.** Buscar el `.uproject` (`Glob **/*.uproject`), leer `EngineAssociation` y la lista de módulos. Leer `.mcp.json` (puerto). Si el `CLAUDE.md` del juego trae la tabla de dueños por carpeta, leerla ahora.
1b. **Tres chequeos fijos (verificados en 7 rondas de TableFlyer, 8 y 9-nov):**
   - **¿Hay un juego empaquetado abierto?** `tasklist | findstr /i <Proyecto>.exe`. Si la persona está jugando: trabajar sin ventana (`-RenderOffscreen -ResX=1920 -ResY=1080`, editor y compilación en `BelowNormal`, `-MaxParallelActions=2`) y NO archivar el build en su carpeta (el `.exe` bloqueado hace fallar el archive con `Access to the path ... is denied`). Archivar en otra carpeta o copiar `Saved/StagedBuilds/Windows` con robocopy.
   - **Atajo verificado:** `python scripts/setup_editor.py` (con el editor abierto y el MCP arriba) deja listos los dos ajustes de abajo (Python remoto y freno de segundo plano) y termina en `SETUP_OK`.
   - **Python remoto en el editor.** Plugins `PythonScriptPlugin` y `EditorScriptingUtilities` con `"TargetAllowList": ["Editor"]`; con el editor abierto, por MCP `ConfigSettingsToolset.SetSectionProperties` container `Project`, category `Plugins`, section `Python`, `{"bRemoteExecution":true}` + `SaveSection` (sin reiniciar). Probar: `python scripts/upy.py -c "print('ok')"` (cliente sobre `remote_execution.py` del motor). Con esto se importa, se crean materiales, se ponen actores y se hacen renders con `import unreal`, cosa que `execute_tool_script` no permite.
   - **Python con rutas de Windows siempre en archivo.** Escribir el script con la herramienta de archivos y correrlo (`python archivo.py` o `upy.py archivo.py`). Nunca heredoc de Bash: `'''` y `\C...` lo rompen (`unexpected EOF`, `unicodeescape`; 3 veces). En el código, rutas con `/` o strings crudos `r''`.
2. **Editor y MCP con una llamada de lectura real.** Ver `/mcp` conectado no prueba nada. Correr:
   `python .claude/skills/ue-session-preflight/scripts/mcp_check.py --url http://127.0.0.1:<puerto>/mcp --expect-map /Game/Maps/<Mapa>`
   Hace ping jsonrpc válido (`{"jsonrpc":"2.0","id":99,"method":"ping"}`; un `{}` deja un error en el log), `initialize` (sesión), `SceneTools.get_current_level` y `EditorAppToolset.IsPIERunning`. Da VERDE, AMARILLO o ROJO.
   - Qué proyecto responde: `list_toolsets` NO trae `_meta` con `projectName` ni `engineVersion` y `serverInfo` llega vacío (verificado en 5.8.4). Se reconoce por la ruta del nivel actual. Si no es el mapa esperado, puede haber otro editor en el mismo puerto.
   - Versión: leer `LogInit` del log del editor (`grep -a "Engine Version" Saved/Logs/<Proyecto>.log`). Si es 5.8.0 o 5.8.1, avisar: hay reportes de MCP que no inicia.
   - PIE corriendo: amarillo (no editar assets). Una compilación en curso no se ve por MCP: si el editor no responde, preguntar.
   - Si falla: máximo 2 reintentos y reportar la causa probable (servidor no iniciado, puerto distinto, editor compilando, versión). No seguir llamando a ciegas.
   - **Freno del editor sin foco (paso fijo).** Con el editor en segundo plano PIE corre a 3 fps ("max tick rate 3" en el log) y las pruebas por MCP dan resultados falsos sin avisar (verificado). Apagar `bThrottleCPUWhenNotForeground` (Editor Preferences > General > Performance > "Use Less CPU when in Background"; clase `UEditorPerformanceSettings`, `EditorPerformanceSettings.h` de 5.8). Por MCP: `ConfigSettingsToolset.SetSectionProperties` con container `Editor`, category `General`, section `EditorPerformanceSettings`, valores `{"bThrottleCPUWhenNotForeground":false}`, y luego `SaveSection` (verificado: de 3 a ~60 fps). Es escribir una preferencia del editor: avisar a la persona.
   - **Comandos de Unreal desde PowerShell (paso fijo).** Git Bash convierte `/Game/...` y `/Engine/...` en `C:/Program Files/Git/...` y daña rutas de mapas, `-dest=` e importaciones. Si no hay otra, `MSYS_NO_PATHCONV=1`.
3. **Git.** `git status --porcelain`, `git branch --show-current`, `git log -1 --oneline`, `git fetch` y `git status -sb` para ver si hay atraso. Si hay cambios sin commit: parar y proponer el commit (los `.uasset` modificados solo se respaldan si están en un commit). Nunca `push --force`, `rebase` de ramas ya subidas ni squash sobre main.
4. **Bloqueos LFS y dueños.**
   - `git lfs locks` (todos) y `git lfs locks --path Content/<Carpeta>` (la zona de trabajo). Para JSON, agregar `--json`.
   - Cruzar con la tabla de dueños por carpeta. Un bloqueo ajeno en la zona de trabajo significa no tocar ese archivo.
   - Confirmar que los binarios son bloqueables: `git check-attr lockable filter -- Content/Prueba.uasset` debe decir `lockable: set` y `filter: lfs` (`.gitattributes` con `*.uasset lock` y `*.umap lock`).
   - Antes de editar un `.uasset` por MCP, tomar el bloqueo: `git lfs lock Content/<Ruta>/<Asset>.uasset`. Se libera con `git lfs unlock`. Sin bloqueo, el conflicto no se puede fusionar.
5. **Respaldo.** Con el árbol limpio: `git branch backup/<AAAAMMDD>-<tarea>` (marca el commit sin cambiar de rama). Para algo más largo, una rama propia por tarea. No usar git worktrees con UE (cada copia arrastra `Intermediate/` y `Binaries/`).
6. **Mapa del proyecto** (todo en el chat, máximo unas 25 líneas, sin pegar archivos enteros). Primero el script, que solo lee y da mapas, módulos, plugins, Data Tables, clases C++ y errores del log en menos de 25 líneas:
   `powershell -File .claude/skills/ue-session-preflight/scripts/project-map.ps1 -ProjectDir <carpeta del .uproject>`
   Si hace falta más detalle, a mano:
   - Mapas: `git ls-files "*.umap"` (solo carpeta y nombre).
   - Módulos y plugins: bloques `Modules` y `Plugins` del `.uproject`, más `Source/*/*.Build.cs`.
   - Clases C++: `grep -rlE "UCLASS|USTRUCT|UENUM" Source --include=*.h` y, por archivo, el nombre de la clase.
   - Data Tables: `git ls-files "Content/**/DT_*.uasset"` y los CSV fuente (`Content/Data/Source/*.csv`).
   - Convenciones vistas (`BP_`, `DT_`, `L_`) y carpetas con dueño.
   - Errores del log: `grep -aE "Error:|Fatal|Ensure condition failed|LogPython: Error|LogCompile.*error" Saved/Logs/<Proyecto>.log | tail -30`. Leer con `grep -a`; el log puede estar abierto por el editor.
   - Por MCP, solo lo necesario: `describe_toolset` de los toolsets que se van a usar, no de todos.
7. **Reporte** (máximo 15 líneas):

```
Editor/MCP : OK  nivel /Game/Maps/<Mapa>, puerto 8000, sin PIE (mcp_check VERDE)
Versión    : OK
Git        : ALERTA  2 archivos sin commit en Source/
LFS        : OK  0 bloqueos ajenos en Content/Mapas
Respaldo   : backup/20261112-vuelo creado
Mapa       : 3 mapas, 14 clases C++, 6 DT, 2 errores en el log (resumen)
Semáforo   : verde / amarillo (solo lectura) / rojo (no escribir)
```

Verde: seguir. Amarillo: solo lectura hasta resolver. Rojo: no escribir. Después de verde, seguir con `ue-mcp-safe-edit`.

## Trampas

- Nunca `--dangerously-skip-permissions` con el plugin cargado. `ProgrammaticToolset.execute_tool_script` no es Python libre (sandbox sin `import unreal`), pero encadena cualquier herramienta de escritura. El puerto no tiene autenticación: no exponerlo, ni por Remote Control.
- Con tool search (por defecto) `tools/list` solo muestra 3 metaherramientas (`list_toolsets`, `describe_toolset`, `call_tool`). Que no aparezca `BlueprintTools.create` no es un error.
- Recompilar C++ exige cerrar el editor y la sesión MCP se cae: al reabrir, nuevo `initialize` y otra vez `mcp_check.py`. No hay proxy en el motor instalado (`ModelContextProtocol/Extras/Proxy` no existe en 5.8.4).
- El Git integrado del editor no maneja LFS ni bloqueos. Hace falta UEGitPlugin (issues abiertos de 5.8: #248, #251, #242).

## Sin verificar (confirmar el día 1, cada uno en 1 a 2 minutos)

- Que `git lfs locks` funcione con el host elegido (GitHub sí; Azure DevOps sin verificar): `git lfs locks` en el repo y ver que no dé error de servidor.
- La forma exacta del valor de `get_current_level` (texto o dict): `mcp_check.py` acepta las dos; mirar la línea `NIVEL` la primera vez.
- Si 5.8.4 arregla el MCP que no iniciaba en la 5.8 estable: abrir el editor, `ModelContextProtocol.StartServer` y ver el log.

## Pruebas de la skill

`python -I .claude/skills/ue-session-preflight/tests/test_project_map.py` (3 pruebas sobre un proyecto falso) y `python -I .claude/skills/ue-session-preflight/tests/test_mcp_check.py` (4 pruebas con un servidor MCP falso). Sin Unreal. `mcp_check.py` usa el cliente de `ue-viewport-eyes/scripts/ue_capture.py`.
