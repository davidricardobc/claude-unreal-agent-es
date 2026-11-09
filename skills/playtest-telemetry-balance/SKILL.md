---
name: playtest-telemetry-balance
description: Registra eventos de partida a CSV en Unreal Engine 5.8 (subsistema C++ o logger Python), resume los playtests (duración, muertes por causa, tiempo hasta la primera muerte, uso y daño por arma o pieza, tasa de victoria, outliers) y escribe propuestas de balance en markdown que una persona aprueba antes de tocar tablas. Genérica, sirve para cualquier proyecto. Frases disparadoras - "/playtest", "analiza el playtest", "resume la telemetría", "qué arma está rota", "propón ajustes de balance", "agrega telemetría al juego", "balance proposals from playtest".
---

# playtest-telemetry-balance

Telemetría propia en CSV, un resumen en markdown y propuestas pendientes de aprobar. Los números orientan; la decisión es humana. No usar CSV Profiler para balance (es de rendimiento y un hilo reporta que sus estadísticas personalizadas no salen en builds empaquetados, sin resolver).

## Formato del CSV (una fila por evento, con encabezado)

`ts,session,build,round,player_id,event,subject,value`

- `ts`: segundos desde el inicio de la sesión. `build`: versión del juego, para comparar antes y después de un ajuste.
- `event`: `spawn`, `death` (subject = causa), `damage` (value = daño, subject = arma), `use` (subject = arma o pieza), `round_end` (subject = loadout o pieza, value = 1 gana, 0 pierde), `session_end`. Se pueden agregar otros; el resumen los ignora.
- Ejemplo ficticio: `examples/sample_telemetry.csv`.

## Piezas (en `.claude/skills/playtest-telemetry-balance/scripts/`)

- `TelemetrySubsystem.h/.cpp`: plantilla C++ de `UGameInstanceSubsystem`. Escribe a `<Proyecto>/Saved/Telemetry/telemetry_<sesión>.csv`, UTF-8 sin BOM, agregando línea por línea (un cierre brusco no pierde datos). Copiar a `Source/<Modulo>/`, cambiar `MYGAME_API`, compilar con el editor cerrado (UCLASS nuevo). Llamar `LogEvent(Event, PlayerId, Subject, Value)` desde C++ o Blueprint.
- `telemetry_logger.py`: mismo formato, para bots, simulaciones o scripts de editor.
- `analyze_playtest.py`: resume y propone. Solo biblioteca estándar de Python 3.

## Flujo de `/playtest`

1. **Preparar.** Confirmar que el build incluye el subsistema y fijar `BuildId`. Borrar o mover los CSV viejos de `Saved/Telemetry/` para no mezclar sesiones (o conservarlos si se quiere comparar).
2. **Jugar.** La persona juega la sesión (o corre bots). Pedir al menos 3 sesiones antes de proponer cambios; una sola no basta.
3. **Recoger.** Copiar `Saved/Telemetry/*.csv` a `docs/playtests/<fecha>/` para que queden versionados.
4. **Resumir.** `python scripts/analyze_playtest.py docs/playtests/<fecha> --out docs/playtests/<fecha>.md [--min-n 5] [--z 2.0]`. Termina con `KIT_OK`. Un outlier es un valor a más de `--z` desviaciones robustas (MAD, o desviación media si MAD es 0) de la mediana. La tasa de victoria se prueba contra la tasa global con una prueba binomial (sirve con 2 loadouts) y exige `n >= --min-n`.
5. **Revisar con la persona.** Leer el markdown: la tabla de propuestas trae subject, señal, ajuste sugerido, columna `tabla/columna` por completar y casilla `[ ]` de aprobación. Las heurísticas son simples: completar con criterio y descartar las que no tengan sentido.
6. **Aprobar.** Solo con el "sí" explícito de la persona por cada fila se edita el CSV fuente de la tabla (ver skill `gdd-to-datatables`: validar, importar con respaldo). Anotar el cambio y el motivo en el mismo markdown.
7. **Repetir.** Jugar con el nuevo `build` y comparar contra el resumen anterior.

## Reglas

- El script nunca toca tablas ni assets: solo lee CSV y escribe un `.md`.
- Muestras chicas (`n < --min-n`) no generan propuesta de tasa de victoria. Decirlo en el reporte.
- No inventar causas: el resumen dice qué pasó, no por qué. Para el porqué, ver el replay o jugar de nuevo.
- Ajustes pequeños (5 a 10 por ciento) y uno a la vez, para saber qué movió el resultado.
- Sin contenido de un juego concreto en esta skill: los ejemplos son ficticios.

## Pruebas

`python tests/test_playtest.py` (datos ficticios y funciones puras) imprime `KIT_OK test_playtest`.

## Estado (verificado el 9-nov-2026, UE 5.8.4)

- `TelemetrySubsystem` compila y escribe `Saved/Telemetry/telemetry_<sesion>.csv` en el editor (PIE) y en un build empaquetado (en el build queda en `<Build>/<Proyecto>/Saved/Telemetry/`). 6 sesiones reales analizadas en TableFlyer.
- Sin probar: multijugador (cada GameInstance escribe su archivo y los eventos pueden duplicarse: registrar solo en la autoridad o agregar el `net_mode` a `subject`) y `telemetry_logger.py` dentro del editor.
- Las heurísticas de `propose()` (porcentajes, umbral z) son un punto de partida, no calibradas.

## Verificado en TableFlyer (ronda 8, 9-nov-2026, UE 5.8.4)

- `TelemetrySubsystem` compila y escribe en 5.8.4 (6 sesiones reales, 95 eventos en `Saved/Telemetry`).
- Nuevo en `analyze_playtest.py`: tabla por loadout (el subject del último `spawn` de la sesión, eventos por minuto), que sirve a juegos sin rondas ni victorias, y tabla de eventos propios del juego (conteo y media de value).
- Trampa: `round_end` con otro valor (un tiempo) da tasas de victoria sin sentido. El tiempo va en su propio evento (`trial_time`).
