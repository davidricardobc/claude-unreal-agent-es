# Lecciones de Unreal Engine 5.8 de un agente real (genéricas, verificadas)

Recogidas en 7 iteraciones de un juego arcade de vuelo pequeño (TableFlyer) construido por el agente con UE 5.8.4 en una laptop con Windows (GTX 1660 Ti). Cada línea se verificó en esa máquina, salvo que diga "sin verificar".

## Editor, MCP y Python

- El servidor MCP de Epic arranca con `UnrealEditor.exe <proyecto> -ModelContextProtocolStartServer -ModelContextProtocolPort=8123`. Envía el encabezado `Mcp-Session-Id` en cada llamada. `call_tool` recibe el nombre LARGO del toolset (`editor_toolset.toolsets.scene.SceneTools`) más el nombre corto de la herramienta.
- Sondea el servidor con un ping JSON-RPC válido (`{"jsonrpc":"2.0","id":99,"method":"ping"}`); un `{}` vacío deja un error en el log.
- `ProgrammaticToolset.execute_tool_script` es un sandbox: no hay `import unreal` y exige un `def run()` que devuelva un dict. Sirve para agrupar llamadas MCP.
- Python real en el editor abierto: activa `PythonScriptPlugin` + `EditorScriptingUtilities` (solo Editor), luego pon `bRemoteExecution=true` (Project > Plugins > Python, funciona con `ConfigSettingsToolset.SetSectionProperties` sin reiniciar) y usa el `remote_execution.py` del motor (ver `tools/upy.py`).
- Un editor en segundo plano frena PIE a 3 fps sin avisar ("max tick rate 3"). Apaga `bThrottleCPUWhenNotForeground` (EditorPerformanceSettings) antes de cualquier prueba en PIE.
- Git Bash convierte los argumentos `/Game/...` en rutas de Windows. Corre los comandos de Unreal desde PowerShell o con `MSYS_NO_PATHCONV=1`.
- Editor sin ventana mientras otra persona usa el PC: `-RenderOffscreen -ResX=1920 -ResY=1080`, prioridad BelowNormal. PIE, las capturas y HighResShot funcionan.
- Cambiar propiedades con `set_editor_property` de Python NO vuelve a ejecutar `OnConstruction`. `ObjectTools.set_properties` del MCP sí. Aplica el layout también en `BeginPlay`.
- Duplicar un mapa y cargarlo en la misma llamada de Python tumba el editor ("World Memory Leaks", EditorServer.cpp). Duplica y guarda en una llamada; `collect_garbage()` y `load_level` en otra.
- Diferencias de nombres en Python: `enable_volumetric_fog` (no `volumetric_fog`); `MaterialEditingLibrary` no puede conectar Clear Coat (no hay CustomData en `MaterialProperty`).

## Probar el juego sin manos

- `SlateInspector.PressKey` no llega al juego en PIE. En su lugar, agrega al pawn ganchos `UPROPERTY(EditAnywhere, Transient, Category="Debug")` (teletransporte, disparo, dash, nombre de captura, comando de consola) y cámbialos con `set_properties` sobre `/Game/Maps/UEDPIE_0_<Mapa>.<Mapa>:PersistentLevel.<Pawn>_0`. El Tick los consume.
- Registra cada evento de juego con un prefijo fijo y busca en el log con grep: la línea de log es la prueba, no "se ve bien".
- Capturas con HUD: `FScreenshotRequest::RequestScreenshot(path, true, false)` desde el pawn. `CaptureEditorImage` con dos monitores dio una imagen ilegible de 1280x313.
- Un gancho de teletransporte vuelve rápidas las pruebas zona por zona: un nivel completo (13 capturas) en una sola sesión de PIE.

## Render

- Mide el sujeto antes de encuadrar. En un mundo a escala 100x (un escritorio de 400 m) los aviones miden de 1,6 a 2,6 m: la cámara va de 3 a 8 m, no a 40.
- Alta resolución sin ventana: en PIE, un gancho del pawn ejecuta `HighResShot 1920x1080 filename=X` con un `ACameraActor` libre como view target.
- Clips: graba cuadro por cuadro desde el motor (`FApp::SetUseFixedTimeStep(true)`, `SetFixedDeltaTime(1/30)`, un `RequestScreenshot` por tick) y une con ffmpeg. La captura de pantalla falló cuando había otra ventana encima.
- Las motas de polvo con materiales translúcidos aditivos o iluminados brillan por todas partes ("cielo estrellado"). Enmascáralas en C++ probando cada mota contra el volumen de luz (rayo de la ventana o cono de la lámpara).
- Luz puntual con `use_inverse_squared_falloff=False`: la intensidad es un multiplicador sin unidad; 5200 volvió la escena blanca, 1.0 es un relleno suave.

## C++ y juego

- Los `USTRUCT`/`UPROPERTY`/clases nuevos necesitan una compilación completa con el editor cerrado; Live Coding no los agrega.
- Proyectiles que lanza el jugador: `SpawnActorDeferred` + configurar + `FinishSpawning`, o el primer overlap llega antes de que se conozca al dueño.
- Dash con perfil de velocidad lineal: integra la distancia restante exacta (D * alpha^2) por cuadro; velocidad * dt se pasaba ~15 % a 60 fps.
- Daño por choque en un pawn con barrido: refleja el rumbo al impactar (dir - 1.6 * dot * N) o el pawn se arrastra contra la pared y muere en menos de un segundo.
- Vuelo libre con loops: guarda la mira como cuaternión y rota en el marco local (`Aim = Aim * FRotator(dPitch, dYaw, 0).Quaternion()`), sigue con `FQuat::Slerp` y mueve el spring arm con `SetWorldRotation` (no con la rotación del control). Nivela automáticamente solo cuando la nariz no está cerca de la vertical.
- Componentes en tiempo de ejecución: `NewObject` + `SetupAttachment` + `RegisterComponent` en `BeginPlay` funciona, incluidos los overlaps. Un actor lanzado con spawn diferido ignoró una propiedad de escala: escala el actor.
- Los objetos `USoundClass` creados en tiempo de ejecución no se registran solos: llama a `AudioDeviceManager->RegisterSoundClass`. Nunca leas `GetSoundClassCurrentProperties` desde el hilo de juego (assert en el hilo de audio, pantalla negra en el juego empaquetado).

## Empaquetado

- BuildCookRun con los plugins MCP de Epic: agrega una regla de `GameFeatureData` a `AssetManagerSettings` o el cook falla con ExitCode=25; deja los plugins MCP con `TargetAllowList: ["Editor"]`.
- No uses `-SkipCookingEditorContent` cuando un plugin como Landmass referencia contenido del editor (ExitCode=25, "marked NeverCook").
- Un proyecto C++ vacío empaquetado para Win64 Development pesa ~650 MB sin pdb: mide el tamaño desde el primer día.
- Prueba siempre el .exe CON sonido. Si debe quedar en silencio, siléncialo con la configuración del propio juego (`-ini:Game:[/Script/Module.Settings]:bStartMuted=True`).
- Si el paso de archivado falla porque el .exe está abierto ("Access ... is denied"), el build en `Saved/StagedBuilds/Windows` ya está completo: cópialo.
- Mide los fps con la máquina sola; otro juego o el editor abierto dieron números de 3 a 5 veces peores.

## Audio (efectos de sonido generados con un servicio de IA)

- Mide antes de confiar: un ambiente de sala en bucle que "sonaba a estática" era ruido de banda ancha más 84 % de energía infrasónica y un offset DC. Filtro pasa altos a 80 Hz, quitar el DC, fades de 2/20 ms, normalizar por RMS activo.
- La planitud espectral entre 200 Hz y 16 kHz detecta ruido; en toda la banda, el infrasonido lo esconde.
