# Lecciones

## Reglas accionables (léelas primero)

1. Antes de nada: ¿está corriendo un build empaquetado del juego? Si es así, trabaja sin ventana (BelowNormal, 2 hilos de compilación) y no archives el build encima.
2. Python dentro del editor por ejecución remota (`upy.py`). Los scripts van en un archivo, nunca en un heredoc de shell.
3. Las herramientas de línea de comandos de Unreal, desde PowerShell (Git Bash reescribe `/Game/...`). Apaga "Use Less CPU when in Background" antes de cualquier prueba en PIE.
4. Ganchos `Debug*` en C++ (teletransporte, captura con HUD, comando de consola, acciones del jugador) y logs con prefijo: prueba sin manos con `set_properties` del MCP y busca en el log con grep.
5. Compila con el editor cerrado. Los cambios de propiedades desde Python no vuelven a ejecutar `OnConstruction`: aplica el layout también en `BeginPlay`.
6. Duplica un mapa y cárgalo en llamadas separadas, con `collect_garbage()` en medio.
7. Renders: mide el sujeto y la escena primero. En un mundo a escala 100x, la cámara va a 3 a 8 m de un avión de 2 m.
8. Prueba el juego empaquetado CON sonido (siléncialo por configuración). Mide los fps con la máquina sola.
9. Si el archivado falla porque el exe está abierto, el build en staged ya está completo: cópialo.
10. Mata solo tu propio PID.

## Registro

- Ronda 2 · El editor en segundo plano corre PIE a 3 fps ("max tick rate 3") y las pruebas por MCP dan resultados falsos sin avisar. Arreglo: `bThrottleCPUWhenNotForeground=false` · verificado (de 3 a ~60 fps).
- Ronda 2 · `SlateInspector.PressKey` no llega al juego en PIE; un gancho `UPROPERTY(Transient)` cambiado con `set_properties` sí · verificado.
- Ronda 3 · Daño por choque en un pawn con barrido: refleja el rumbo (dir - 1.6*dot*N) o se arrastra contra la pared y muere en menos de un segundo · verificado en el log.
- Ronda 4 · Un `USoundClass` creado en tiempo de ejecución no se registra solo: `AudioDeviceManager->RegisterSoundClass` · verificado (volumen del bus leído de vuelta: 0.251).
- Ronda 5 · La "estática" del audio era un ambiente en bucle con 84 % de energía infrasónica y offset DC; mide la planitud espectral entre 200 Hz y 16 kHz · verificado con numpy.
- Ronda 6 · Clips: graba cuadro por cuadro desde el motor con un paso fijo de 1/30 s; la captura de pantalla falló cuando había otra ventana encima · verificado (30 fps exactos).
- Ronda 7 · Vuelo libre con loops: mira como cuaternión rotada en el marco local, seguimiento con slerp, spring arm movido con `SetWorldRotation` · verificado (el arriba de la cámara contra el arriba del avión se mantuvo en 0.95 durante un loop).
- Ronda 8 · Blender -> UE 5.8 (Interchange): FBX y GLB conservan la escala y los ejes; un armature que no se llama "Armature" agrega un hueso raíz; el FBX "All Actions" hornea cada acción en cada rig, el GLB no · verificado con un asset de prueba.
- Ronda 8 · Un pawn para pruebas de vuelo con guion debe devolver su velocidad real en `GetVelocity()` y volver a sincronizar su mira en `SetInitialSpeed` · verificado (5/5 maniobras).
- Ronda 9 · Los campos de `HitResult` no se pueden leer con `get_editor_property` en Python 5.8.4; `to_tuple()` sí funciona. Un parser equivocado hizo que cada traza pareciera "sin colisión" durante un día · verificado.
- Ronda 9 · Correr una skill en un proyecto real encontró 10 errores que sus pruebas sin conexión nunca vieron (API vieja, falsos verdes silenciosos, carga asíncrona) · verificado.
