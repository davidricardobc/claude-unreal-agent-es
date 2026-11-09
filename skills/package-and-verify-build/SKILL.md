---
name: package-and-verify-build
description: Empaqueta el juego de Unreal 5.8 como build Win64 Development con RunUAT BuildCookRun, revisa el log de UAT, mide y comprime el zip TeamName_GameName (menos de 1 GB, o butler si es más grande), hace el smoke test del ejecutable, guía la prueba en otra máquina y la subida a itch con butler (siempre --dry-run primero y solo con el sí explícito de la persona autorizada). Úsala cuando pidan "empaqueta el build", "build de prueba", "build final", "BuildCookRun", "falló el cook", "el zip pesa mucho", "sube a itch", "butler push", o en inglés "package the game", "cook and package", "verify the build", "upload to itch".
---

# package-and-verify-build

Probada en TableFlyer (8 empaquetados) y en un proyecto C++ en blanco de UE 5.8.4.

## Reglas duras

- `butler push` es publicar. Primero `--dry-run`, y el push real solo con el sí explícito de la persona autorizada en el chat (`-ConfirmadoPor <nombre>` es obligatorio con `-Real`). Aprobar el build no es aprobar la subida.
- Nunca leer, mostrar ni pegar `BUTLER_API_KEY` ni el archivo de credenciales de butler. `butler login` lo hace un humano.
- Enviar un build a un concurso, una tienda o un cliente lo hace un humano. Un agente no envía.

## Marcadores

| Marcador | Qué es | Ejemplo |
|---|---|---|
| `<UE_ROOT>` | Carpeta del motor | `C:\Program Files\Epic Games\UE_5.8` |
| `<Proyecto>` | Ruta completa del `.uproject`, corta y sin espacios | `C:\Proj\MiJuego.uproject` |
| `<Salida>` | Carpeta de `-archivedirectory` | `C:\Proj\out` |
| `<NombreExe>` | Ejecutable del build | `MiJuego.exe` |
| `<TeamName>_<GameName>` | Nombre exacto del zip | `Equipo_MiJuego.zip` |
| `<usuario>/<juego>:<canal>` | Destino en itch, minúsculas | `cuenta/mi-juego:windows-test` |

## Prerrequisitos (una vez por máquina)

1. Visual Studio 2022 17.14 o más, o VS 2026 (Epic recomienda 2026). Cargas: Desarrollo de escritorio con C++, Desarrollo de juegos con C++, Desarrollo de escritorio .NET. Componentes: C++ profiling tools y C++ AddressSanitizer. **Con solo Build Tools falta el .NET Framework SDK** y el editor target (y BuildCookRun) fallan con `Could not find NetFxSDK install dir` en `SwarmInterface`. Arreglo verificado (una vez, con admin): VS Installer > Build Tools > Modificar > Componentes individuales > ".NET Framework 4.6.2 targeting pack" y ".NET Framework 4.8.1 SDK" (o la carga "Desarrollo de escritorio .NET"). Ojo: ese instalador puede subir MSVC a 14.51; UBT avisa "newer than latest preferred version 14.50" pero compila y empaqueta bien. Si da problemas, agregar el componente `Microsoft.VisualStudio.Component.VC.14.50.18.0.x86.x64`.
2. MSVC mínimo 14.38 (recomendado 14.50). Windows SDK mínimo 10.0.22621.0, recomendado 10.0.26100 o más: instalar ambos (hay discrepancia en 5.8.0). .NET 10 si es VS 2026.
3. Proyecto en ruta corta sin espacios (`C:\Proj`): el límite de 260 caracteres de Windows rompe cooks.
4. Disco libre para `Intermediate`, `Saved\Cooked` y el staged. Cronometrar el cook en frío con la plantilla vacía y anotar el tiempo.
5. 7-Zip en el PATH. butler en `C:\butler` y en el PATH (`butler version`).

## Pasos

1. **Preparar.** `git status` limpio y `git pull` hecho. Mejor con el editor cerrado (evita DLL bloqueadas). Si el editor tiene que seguir abierto, agregar `-nocompileeditor` (`package.ps1 -NoCompileEditor`): BuildCookRun no intenta recompilar el editor en uso (verificado, empaquetó en 224 s). Ruta y espacio libre revisados. Correr desde PowerShell, no Git Bash.
2. **Confirmar banderas** (el día 1, una vez; es la verificación de todas las banderas de abajo):
   `& "<UE_ROOT>\Engine\Build\BatchFiles\RunUAT.bat" BuildCookRun -help`
   Ya verificado en 5.8.4 (la máquina de prueba (laptop, GTX 1660 Ti) y `ProjectParams.cs`): `-iostore`, `-compressed`, `-prereqs`, `-NoP4`, `-UTF8Output` existen. `-compressed` y `-nocompileeditor` no salen en `-help` pero existen. BuildCookRun compila también el editor salvo `-nocompileeditor`.
3. **Empaquetar** con `package.ps1` (esta carpeta). Comando que envuelve:
   ```
   & "<UE_ROOT>\Engine\Build\BatchFiles\RunUAT.bat" BuildCookRun -project=<Proyecto> -noP4 -utf8output -unattended `
     -platform=Win64 -targetplatform=Win64 -clientconfig=Development `
     -build -cook -stage -pak -iostore -compressed -prereqs -package `
     -archive -archivedirectory=<Salida> -UbtArgs=-MaxParallelActions=4
   ```
   `-UbtArgs=-MaxParallelActions=4` (parámetro `-Hilos` de `package.ps1`, 4 por defecto) evita que UBT sature una laptop de 4 hilos; verificado. `package.ps1 -DryRun` imprime el comando sin correr nada.
   Si el proyecto tiene los plugins del MCP (`AllToolsets`), antes del primer cook agregar la regla de `GameFeatureData` (ver errores típicos) y dejar los plugins del MCP con `"TargetAllowList": ["Editor"]` en el `.uproject` para que no entren al build.
   Mapas: `-map=MapaA+MapaB`, o la lista de Project Settings > Packaging. Poner también Game Default Map y Editor Startup Map, o el build abre un mapa vacío.
4. **Revisar el log de UAT** (`package.ps1` lo deja en `<Salida>\uat-*.log`): buscar `ExitCode=`, `BUILD SUCCESSFUL`, `Error:`. Si falla, abrir el log de cook cuya ruta imprime UAT y resumir los `Error:` (el motivo no está en el resumen final). Ver errores típicos abajo.
5. **Medir y comprimir** con `verify-build.ps1`: quita `*.pdb`, mide el staged, hace `7z a -tzip -mx=9 <TeamName>_<GameName>.zip` (sin 7-Zip usa .NET ZipFile, menos compresión) y calcula el SHA256. Rechaza nombres que no sean `TeamName_GameName.zip`. No usar `Compress-Archive` (falla sobre 2 GB y escribe rutas con barra invertida).
6a. **Siempre CON sonido.** Nunca dar por bueno un smoke test con `-nosound`: esconde todo error de audio (TableFlyer ronda 4: `Assertion failed: IsInAudioThread()` con pantalla negra solo aparecía con sonido). Si no debe sonar (alguien usa el PC), silenciar con la configuración del juego, no apagando el audio: por ejemplo `-ini:Game:[/Script/<Modulo>.<ClaseSettings>]:bStartMuted=True`. El log debe mostrar el dispositivo de audio creado (`LogAudioMixer: Initializing audio mixer`). Para probar otro mapa o un viaje entre mapas sin manos: `<Mapa>` como primer argumento o `-ExecCmds="open /Game/Maps/<Mapa>"`. Verificado.
6. **Smoke test** (lo hace el mismo script): arranca `<NombreExe> -log -windowed -ResX=1280 -ResY=720`, espera 60 s, comprueba que sigue vivo cualquier proceso dentro del staged (el `.exe` de la raíz es un lanzador que abre `<Proyecto>\Binaries\Win64\<Proyecto>.exe`; se cierran todos) y busca `Fatal error` en el log más nuevo. Es solo humo: no reemplaza el paso 7.
7. **Otra máquina.** Copiar el zip a un Windows 10 u 11 que no tenga Unreal ni Visual Studio. Descomprimir en carpeta nueva, abrir, jugar 10 minutos (menú, partida, fin, salir). Si pide VC++, anotarlo para la página de itch. La regla pide que corra sin instalar nada más. Hacerlo viernes noche y sábado, no el domingo.
8. **Subida a itch** (solo con el sí; ver reglas duras). Con `butler-push.ps1`:
   - `--dry-run` siempre primero: `butler push --dry-run <Salida>\Windows <usuario>/<juego>:windows-test`
   - Pruebas al canal `windows-test`; el final a `windows`. Un canal con `win` o `windows` queda etiquetado Windows.
   - Carpeta: `butler push <Salida>\Windows <usuario>/<juego>:windows --userversion <version> --ignore "*.pdb"`
   - Zip tal cual (sin verificar, `butler push --help` en 1 minuto): `-ComoZip` agrega `--no-auto-unzip`. Sin esa bandera butler descomprime.
   - La página del juego debe existir antes y quedar en borrador o restringida hasta el final.
9. **Anotar** en `docs/builds.md`: fecha, commit, tamaño, SHA256, resultado del smoke test y de la otra máquina (lo escribe `verify-build.ps1`).

## Nombre del zip (`TeamName_GameName`, el formato que piden muchos concursos)

- butler NO conserva el nombre del zip: itch genera el archivo de descarga a partir del juego y el canal (por ejemplo `juego-canal.zip`). Con butler no se puede garantizar `TeamName_GameName`.
- Regla: el zip que se entrega es el que crea `verify-build.ps1` con ese nombre exacto, y se sube a mano por el formulario web del concurso (o al juego en itch como archivo, por la página). butler sirve para distribución y builds grandes, no para el nombre.
- Si el destino acepta solo un enlace a itch, preguntar qué nombre ven; sin verificar.

## Si el zip pasa de 1 GB

La regla acepta butler para builds grandes, así que 1 GB no es un muro. Aun así, medir antes de adivinar:
1. Size Map en el editor sobre el mapa principal. Texturas 4K de packs a 2K donde no importan.
2. Cocinar solo los mapas usados (no "cook all"). **No usar `-SkipCookingEditorContent`** (la bandera real; `-skipeditorcontent` es la que UAT pasa al cook): verificado en la máquina, rompe el cook con `ExitCode=25` ("Content is missing from cook ... marked NeverCook") cuando un plugin como Landmass referencia contenido de editor. Referencia: un proyecto vacío ya pesa ~650 MB sin pdb (exe monolítico ~330 MB), así que el tope de 1 GB queda justo: medir desde el día 1.
3. `bCompressed=True` y `PakFileCompressionFormats=Oodle` en `[/Script/UnrealEd.ProjectPackagingSettings]`. Medir con y sin `-compressed`.
4. Desactivar plugins sin uso. WAV de librerías a Ogg. Quitar `.bk2` sin uso. Borrar `*.pdb`.

## Errores típicos

| Síntoma | Qué hacer |
|---|---|
| `ExitCode=25 (Error_UnknownCookFailure)` o `ExitCode=1` | Abrir el log de cook, buscar `Error:`. Referencias rotas: agregar `-LogCmds="LogRedirectors verbose"` |
| `Could not find NetFxSDK install dir` (`SwarmInterface`, RulesError) | Falta el .NET Framework SDK en Build Tools: ver prerrequisito 1. Verificado |
| `ExitCode=25` con `Asset manager settings do not include a rule for assets of type GameFeatureData` | El plugin `AllToolsets` del MCP activa GameFeatures. En `DefaultGame.ini`, sección `[/Script/Engine.AssetManagerSettings]`: `+PrimaryAssetTypesToScan=(PrimaryAssetType="GameFeatureData",AssetBaseClass="/Script/GameFeatures.GameFeatureData",bHasBlueprintClasses=False,bIsEditorOnly=True,Directories=((Path="/Game/Unused")),SpecificAssets=,Rules=(Priority=-1,ChunkId=-1,bApplyRecursively=True,CookRule=AlwaysCook))`. Con `bIsEditorOnly=False` el juego da `Ensure condition failed: AssetBaseClassLoaded` al arrancar. Verificado |
| `ExitCode=25` con `Content is missing from cook ... marked NeverCook` (Landmass, `/Engine/EditorMaterials`) | Quitar `-SkipCookingEditorContent`. Verificado |
| Windows pide permiso del firewall al abrir el `.exe` | Normal en Development. No tocar el firewall desde el agente; avisar a la persona |
| "Visual Studio 2022 x64 must be installed" (5.8.1 con VS 2026) | Editor Preferences > General > Source Code > Source Code Editor = Visual Studio 2026, reiniciar. Si no sirve, instalar VS 2022 17.14 al lado |
| Falla el SDK de Windows | Instalar 10.0.22621 y 10.0.26100 |
| Cook falla en proyecto solo de Blueprints (5.8.1) | Hay un hilo abierto. Leer el log y probar con un proyecto C++ |
| El build abre un mapa vacío | Game Default Map y Editor Startup Map, o `-map=` |
| Error 0x80070666 o falta VC++ en PC limpia | Hay `UEPrereqSetup_x64.exe` por `-prereqs`; escribir en la página de itch qué hacer |
| Archive falla con `Access to the path '...\<NombreExe>' is denied` | El juego está abierto (alguien jugando). El staging ya está completo en `<Proyecto>\Saved\StagedBuilds\Windows`: copiarlo con robocopy a otra carpeta en vez de empaquetar otra vez. Verificado |
| Rutas de más de 260 caracteres | Mover el proyecto a `C:\Proj` |
| `butler` rechaza la clave | El salto de línea final de un archivo de clave la rompe; un humano re-hace `butler login` |

## Trampas

- Un build de Development no es Shipping: elegir el que pida el destino.
- No usar CI: un script local basta.
- No subir un zip de otro nombre al formulario: debe ser `<TeamName>_<GameName>`. Nunca subir el que bajó de itch tras un butler push.
- Si una clave sale en un log público, revocarla.

## Sin verificar

- Confirmado el 8-nov-2026 en la máquina: banderas, salida en `<Salida>\Windows\`, lanzador `<Proyecto>.exe` en la raíz, juego real en `<Proyecto>\Binaries\Win64\`, log en `<Proyecto>\Saved\Logs\`. Confirmado el 9-nov-2026 en un proyecto C++ en blanco: compilación, zip de 0,37 GiB y smoke test con sonido.
- Si el zip debe llevar carpeta raíz. El comando actual es `7z a ... .\Windows\*` (sin carpeta).
- `--no-auto-unzip` de butler: `butler push --help`.
- Que `butler` necesita la página creada antes del primer push.
- `-nocompileeditor` solo si el editor ya está compilado; no se usa por defecto.

## Pruebas

`python -I -m unittest discover -s .claude/skills/package-and-verify-build/tests` (Windows PowerShell; sin Unreal, sin red, sin butler). Cubre zip, nombre, SHA256, fila de `builds.md`, validaciones de `butler-push.ps1` y el comando de `package.ps1 -DryRun` (tope de hilos, sin `-SkipCookingEditorContent`). El empaquetado real y el smoke test solo se prueban con un build.
