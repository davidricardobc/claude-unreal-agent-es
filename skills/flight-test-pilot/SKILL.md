---
name: flight-test-pilot
description: Prueba el movimiento de un vehículo o pawn en Unreal Engine 5.8 con maniobras guionadas (despegue, giro de 360, loop, picada, recuperación de pérdida) definidas en JSON o CSV. Registra la trayectoria en CSV, la compara con criterios (tiempo de giro, altitud perdida, estabilidad, sin NaN, sin saltos) y reporta pasa o falla. Incluye ajuste de PID para bots con Ziegler-Nichols simplificado, barrido de ganancias o twiddle contra una planta simulada. Úsala tras tocar el movimiento, las fórmulas de vuelo o los bots. Frases disparadoras - "prueba el vuelo", "corre las maniobras", "¿gira 360 en el tiempo?", "afina el PID del bot", "regresión de vuelo", "flight test", "tune the autopilot", "stall recovery check".
---

# flight-test-pilot

Maniobras repetibles contra el movimiento del pawn, con números en vez de "se siente bien". Sirve para cualquier pawn con movimiento propio (avión, nave, dron, vehículo). No contiene datos de ningún juego: los criterios los pone cada proyecto.

## Piezas (en `.claude/skills/flight-test-pilot/`)

| Archivo | Para qué | Corre en |
|---|---|---|
| `scripts/maneuvers.example.json` | Ejemplo de 5 maniobras para un pawn con modelo de sustentación | datos |
| `scripts/maneuvers.reference_pawn.json` | 4 maniobras que pasan con el pawn de referencia | datos |
| `references/FlightTestPawn.h/.cpp` | Pawn mínimo que cumple el contrato: para probar la skill en un proyecto vacío o copiar el patrón | C++ |
| `scripts/maneuver_script.py` | Carga JSON/CSV, valida, da el stick en el tiempo t | Python puro |
| `scripts/flight_session.py` | Sesión: avanza maniobras, escribe CSV y `run.json`, decide el veredicto | Python puro |
| `scripts/ue_flight_runner.py` | Adaptador del pawn en PIE sobre la sesión | dentro de UE |
| `api.txt` | Llamadas `unreal.*` que usa el runner (todas confirmadas en 5.8.4) | datos |
| `references/automation_test_template.md` | Prueba C++ de Automation (camino más fiable) | dentro de UE |
| `scripts/analyze_flight.py` | Lee los CSV, calcula métricas y reporta pasa/falla | Python puro |
| `scripts/pid_tune.py` | Ziegler-Nichols, barrido y twiddle contra una planta simulada | Python puro |
| `tests/test_flight_test_pilot.py` | 27 pruebas sin Unreal | Python puro |

## Flujo

1. **Contrato con el pawn.** Debe aceptar un stick virtual: `SetVirtualStick(Throttle, Pitch, Roll, Yaw)` (nombre de convención; humanos y bots deberían usar la misma entrada). Si no existe, agregarlo primero. No inventar otra vía.
2. **Escribir maniobras** copiando `maneuvers.example.json`. Cada una: `id`, `duration_s`, `setup` (altitud y velocidad iniciales), `steps` (`t0`, `t1`, `stick`) y `criteria`. También sirve un CSV de pasos `id,t0,t1,throttle,pitch,roll,yaw` (los criterios van en el JSON). Validar: `python -c "import sys;sys.path.insert(0,'scripts');import maneuver_script as m;[print(x['id'],m.validate(x)) for x in m.load_maneuvers('scripts/maneuvers.example.json')]"`.
3. **Correr** (ver `ue-headless`):
   - Python (necesita ticks, por eso modo editor completo): variables `KIT_FLIGHT_MANEUVERS`, `KIT_FLIGHT_MAP`, `KIT_FLIGHT_PAWN_TAG`, y `run-python.ps1 -Mode ExecutePythonScript -TimeoutSec 900 -Script .claude/skills/flight-test-pilot/scripts/ue_flight_runner.py`. `KIT_OK` sale solo si todas las maniobras corrieron y pasaron; si no, `KIT_FAIL <motivo>`. El runner borra los CSV viejos y escribe `run.json`.
   - Automation (recomendado si el bucle de ticks del commandlet no avanza): plantilla C++ y `run-tests.ps1 -Filter "Project.Flight"`.
   - Con el editor abierto, por MCP (verificado en la máquina el 8-nov): `EditorAppToolset.StartPIE` (`options.playMode=PlayMode_InViewPort`, `warmupSeconds`), `IsPIERunning`, `StopPIE`. El input NO se puede mandar con `SlateInspector.PressKey` (no llega al juego). En su lugar, ganchos de depuración en el pawn: una `UPROPERTY(EditAnywhere)` como `DebugStick` (FVector4) o `DebugAction` que el `Tick` lee y aplica; el agente la cambia con `ObjectTools.set_properties` (values como string JSON) sobre `/Game/Maps/UEDPIE_0_<Mapa>.<Mapa>:PersistentLevel.<Pawn>_0` y lee la posición con `ActorTools.get_actor_transform`. Capturas en PIE con `ue-viewport-eyes` (`CaptureEditorImage`). Los ganchos `Debug*` van solo en builds de editor (`#if WITH_EDITOR` o `UPROPERTY` sin efecto en Shipping).
   - Salida: `Saved/FlightTests/<id>.csv` con `t,x,y,z,pitch,roll,yaw,vx,vy,vz` (cm y grados).
4. **Analizar:** `python .claude/skills/flight-test-pilot/scripts/analyze_flight.py --maneuvers <json> --dir <proyecto>/Saved/FlightTests`. Última línea `FLIGHT_PASS` o `FLIGHT_FAIL`; código de salida 0 o 1. Un CSV ausente, con NaN, con menos de 3 muestras o anterior a `run.json` es falla.
5. **Si falla:** cambiar UNA constante por iteración (máximo 5 iteraciones), volver a correr y comparar la métrica. No tocar criterios para que pasen sin decirlo.

## Métricas disponibles

`has_nan`, `time_monotonic`, `duration_s`, `altitude_lost_m`, `altitude_gained_m`, `final_altitude_delta_m`, `min_speed_mps`, `max_speed_mps`, `max_step_jump_m` (detecta teletransportes y atravesar paredes), `turn180_time_s`, `turn360_time_s`, `loop_time_s` (por ángulo de trayectoria, sin saltos de Euler), `settled_{pitch,roll,yaw}_rate_rms` (estabilidad en los últimos 2 s), `max_abs_pitch`, y `stall_recovery_time_s` (con el criterio `recover_speed_mps`). Formato: `{"metrica": {"min": a, "max": b}}`; booleanos `{"equals": false}`. Una métrica que no se pudo calcular falla.

## Ajuste de PID para bots

Solo contra una planta simulada, sin Unreal. Flujo:

1. Medir la respuesta al escalón del pawn real (stick fijo, grabar la tasa o el ángulo). Ajustar `K` (ganancia), `tau` (constante de tiempo), `delay` (retardo) e `integrating` (sí si la salida es un ángulo y la entrada una tasa).
2. `python scripts/pid_tune.py --K 1 --tau 0.4 --delay 0.1 --integrating --method zn` busca la ganancia última `Ku` y el periodo `Pu` (solo P hasta oscilación sostenida) y devuelve ganancias por regla (`classic`, `some_overshoot`, `no_overshoot`, `pi`, `p`).
3. Si la planta no oscila (primer orden sin retardo), no hay `Ku`: usar `--method sweep` (rejilla) o `--method twiddle` (descenso por coordenadas). Costo = IAE (error absoluto integrado) + penalización si el sobrepaso pasa de 15 %.
4. Orden para bots: primero alabeo, luego cabeceo, luego velocidad. Cascada: P de ángulo hacia tasa, PI de tasa con feedforward.
5. Probar las ganancias en Unreal con una maniobra de escalón y la métrica `settled_*_rate_rms`. El modelo es una aproximación: si el pawn real se desvía, volver a medir `K`, `tau` y `delay`.
6. Una tabla de ganancias por categoría de carga o masa (baja, media, alta) en un CSV o Data Table del proyecto.

## Pruebas

`python -m unittest discover -s .claude/skills/flight-test-pilot/tests` (también `python -m py_compile` en cada script). 27 pruebas: giros sintéticos, loop, NaN, teletransporte, recuperación, convergencia de la planta, `Ku`/ZN, twiddle y barrido.

## Trampas

- Con física asíncrona (Chaos) o paso variable la misma maniobra da resultados distintos. Correr 3 veces y comparar con tolerancia de 5 %. Mejor: movimiento propio con paso fijo.
- Euler tiene saltos de ±180 en yaw y gimbal en pitch ±90: por eso el loop se mide con el ángulo de la trayectoria, no con el pitch.
- Unidades: Unreal da cm. Los criterios van en metros y m/s (`--unit-scale 0.01`).
- Un tick por fotograma no es paso fijo. Para pruebas estrictas, fijar los fps (`-benchmark -fps=60`, sin verificar) o avanzar el movimiento con `Dt` fijo en la prueba C++.

## Estado (verificado el 9-nov-2026, UE 5.8.4)

- De punta a punta en un proyecto C++ en blanco: copiar `references/FlightTestPawn.*` a `Source/<Modulo>/` (cambiar `MYGAME_API`), compilar, poner uno en un mapa (ya trae el tag `FlightTestPawn`) y correr el runner con `KIT_FLIGHT_MANEUVERS=scripts/maneuvers.reference_pawn.json`. Resultado: 4/4 PASS y `FLIGHT_PASS` con `analyze_flight.py --unit-scale 0.01`.
- Con el editor abierto: poner las variables `KIT_FLIGHT_*` en `os.environ`, `KIT_FLIGHT_KEEP_EDITOR=1`, y correr el runner con `upy.py` (`runpy.run_path`). El veredicto sale en el log del editor.
- Confirmado en 5.8.4: `get_all_actors_with_tag`, `register_slate_post_tick_callback`, `set_virtual_stick` desde Python, `Rotator(roll, pitch, yaw)`, `editor_request_begin_play/end_play`.
- Sin probar: el modo `-ExecutePythonScript` con el editor cerrado (`run-python.ps1`) y la prueba C++ de Automation de `references/`.

## Verificado en TableFlyer (ronda 8, 9-nov-2026, UE 5.8.4)

- Corrió en Unreal por primera vez: 5 maniobras (crucero, giro 360, subida, acelerar, frenar), `KIT_OK` y `analyze_flight.py --unit-scale 0.01` -> `FLIGHT_PASS`.
- Contrato del pawn, lo que faltaba decir: (1) `GetVelocity()` debe devolver la velocidad real (un pawn que se mueve con offsets da 0 y fallan las métricas de velocidad); (2) `SetInitialSpeed` debe re-sincronizar la mira con la rotación que puso el script, o el pawn vuelve a su rumbo anterior.
- Arreglado en `ue_flight_runner.py`: `KIT_FLIGHT_KEEP_EDITOR=1` no cierra el editor (para correrlo en vivo con `upy.py`) y, si ningún actor tiene el tag (o el tag es `*`), usa el pawn del jugador 0.
- Un juego arcade con tope de pitch no puede hacer `loop`: no poner esa maniobra si el diseño lo impide.
