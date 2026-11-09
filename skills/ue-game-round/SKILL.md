---
name: ue-game-round
description: Ciclo completo de una "ronda" de juego en Unreal Engine 5.8 hecha por un agente - leer el pedido y la memoria, construir en C++ con ganchos de prueba Debug, probar en PIE sin manos (MCP set_properties + log), capturar con HUD, empaquetar y probar el .exe con sonido, y reportar con commits pequeños. Úsala cuando pidan "otra ronda", "siguiente iteración del juego", "agrega estas mejoras y empaqueta", "build de prueba con lo nuevo", "game iteration", "next round", "build, test and package". No es para el envío final a un concurso o tienda ni para renders de presentación solos (ue-render-shots).
---

# ue-game-round

Patrón que salió de 7 rondas seguidas de TableFlyer (8 y 9-nov-2026): cada ronda pidió lo mismo, construir, probar, capturar, empaquetar y reportar, y lo que fallaba casi siempre era el ciclo, no Unreal. Esta skill es el ciclo; el detalle técnico vive en las skills que llama.

## Antes de tocar nada (5 minutos)

1. Leer la memoria del agente (índice, estado del proyecto, última sesión) y el `PROGRESO.md` del juego. Si el pedido toca algo con lección o error anotado, leerlo.
2. `ue-session-preflight`: editor y MCP en verde, Python remoto (`upy.py`), freno de segundo plano apagado, ¿hay un `.exe` del juego abierto? (si sí: trabajar sin ventana y no archivar encima).
3. Partir el pedido en P0/P1/P2 con un "hecho" verificable por cada uno (log, captura o número). Tope de compilaciones y de empaquetados acordado.

## Construir

- Lógica en C++, Blueprints delgados o ninguno. Cada propiedad ajustable en `UPROPERTY(EditAnywhere)` con un comentario de qué hace.
- **Ganchos de prueba desde el principio** (son lo que permite probar sin manos; `SlateInspector.PressKey` NO llega al juego):
  - `UPROPERTY(EditAnywhere, Transient, Category="Debug")` que el agente cambia en PIE con `ObjectTools.set_properties` sobre `/Game/Maps/UEDPIE_0_<Mapa>.<Mapa>:PersistentLevel.<Pawn>_0`, y que el `Tick` consume y pone en cero.
  - Mínimos útiles: `DebugTeleport` (+ yaw/pitch), `DebugScreenshotName` (`FScreenshotRequest::RequestScreenshot(..., true, false)`, con HUD), `DebugConsoleCommand` (`HighResShot`), `bDebugFreeze`, uno por acción del jugador (disparar, dash, cambiar de modo) y un `bDebugLog<Cosa>` que escriba el estado por cuadro.
  - Logs con prefijo fijo (`TF: ...`) en cada evento de juego: el log es la prueba.
- Lo nuevo no debe romper lo viejo: si hay un modo nuevo, detectarlo sin tocar el camino viejo (por ejemplo, por el nombre del mapa) y dejarlo apagado por defecto.
- Compilar con el editor cerrado: `Build.bat <Proyecto>Editor Win64 Development -Project=... -WaitMutex -MaxParallelActions=2` en `BelowNormal`. Live Coding no agrega `UPROPERTY` ni clases.
- Niveles y props por script de Python reejecutable (borra su carpeta y vuelve a armar), guardado en el repo del juego. Los cambios de propiedades por Python no re-ejecutan `OnConstruction`: aplicar el layout también en `BeginPlay` o tocar una propiedad por MCP `set_properties`.
- Duplicar un mapa y cargarlo en llamadas de Python distintas, con `collect_garbage()` en medio (si no, el editor se cae con "World Memory Leaks").

## Probar (PIE sin manos)

1. Un script de prueba por ronda: `start()`, ganchos, `time.sleep`, capturas con nombre `rNN_<cosa>`, `stop()`. Teletransportar a cada zona es mucho más rápido que volar hasta allá.
2. Leer el log y contar eventos (`grep "TF: "`): el "hecho" de cada P0 es una línea del log o un número, no "se ve bien".
3. Mirar las capturas a 800 px (hoja de contacto). Si algo no se ve, sondear el mundo de PIE con Python (`UnrealEditorSubsystem.get_game_world()` + `GameplayStatics.get_all_actors_of_class`) antes de adivinar.
4. Regresión: un PIE corto del modo viejo con los mismos ganchos (daño, enemigos, puntaje en el log).

## Empaquetar y probar

- `package-and-verify-build`. Si el `.exe` está bloqueado, el staging (`Saved/StagedBuilds/Windows`) ya sirve: copiarlo a otra carpeta.
- El `.exe` se prueba **con sonido** (silenciado por configuración si hace falta), 30 a 45 s, 0 errores en el log, y el mapa nuevo cargado (argumento de mapa o `-ExecCmds="open ..."`).
- fps: medir con la máquina sola; otro juego o el editor abiertos dan números falsos.

## Reportar y cerrar

- Commits pequeños por pieza (`git add` con rutas, nunca `-am`), mensaje con qué, por qué y cómo se probó. Sin push.
- `PROGRESO.md` del juego: qué quedó, teclas, qué debe probar la persona, mejoras posibles.
- Memoria del agente: lección o error nuevo con mensaje exacto, causa y arreglo; nota de sesión; fila de eficacia.
- Reporte corto: qué quedó, cómo se prueba, números (fps, tamaño), rutas de capturas, pendientes.

## Trampas vistas

- Editor en segundo plano: PIE a 3 fps sin avisar (apagar `bThrottleCPUWhenNotForeground`).
- Git Bash convierte `/Game/...` en rutas de Windows: comandos de Unreal desde PowerShell o con `MSYS_NO_PATHCONV=1`.
- Python con rutas de Windows en un heredoc: `unicodeescape`. Siempre en archivo.
- Componentes creados en `BeginPlay`: `NewObject` + `SetupAttachment` + `RegisterComponent` funciona. Un actor creado con `SpawnActorDeferred` puede ignorar una propiedad de escala: escalar el actor.
- No matar procesos por nombre (`taskkill /IM`): solo el PID propio.
