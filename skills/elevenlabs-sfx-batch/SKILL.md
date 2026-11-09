---
name: elevenlabs-sfx-batch
description: Pasa de un audio-manifest.csv (id, categoria, prompt en inglés, segundos, loop, prompt_influence, tomas) a WAV listos en Unreal Engine 5.8 con ElevenLabs Sound Effects v3. Valida el CSV, estima el costo con --dry, mide la tarifa real con una prueba de 1 s, genera con tope de créditos sin repetir lo pagado, posprocesa con ffmpeg (WAV 48 kHz, recorte de silencios, bucles con crossfade, loudnorm por categoría, pico real máximo -1 dBTP, QC) e importa a /Game/Audio con Python de Unreal. Úsala cuando la persona a cargo pida generar efectos de sonido, un lote de audio, sonidos de materiales, armas, interfaz o ambientes, o cuando se diga "generate sound effects", "SFX batch", "audio manifest", "import WAV into Unreal", "normalize loudness for the game". No sirve para el sonido continuo de los motores (ver metasound-engine-family) ni para música o voz (otros endpoints).
---

# ElevenLabs SFX en lote, de CSV a Unreal

Herramientas adaptadas de `<AUDIO_LIBRARY>/scripts` (`generar.mjs`, `qc.mjs`, `normalizar.mjs`). Cuesta créditos reales: cada paso que paga lo dice antes.

## Fecha de inicio opcional (apagada por defecto)

- Sin `KIT_START` no hay freno: se genera cuando se pida.
- Si el proyecto tiene un momento antes del cual no debe generarse audio del juego (un concurso, un hito), poner `KIT_START` con fecha ISO y zona explícita, por ejemplo `2030-01-01T00:00:00-05:00`. Antes de esa hora un lote sale con código 3; `--probe` y `--allow-early --only Id` pasan, con máximo 10 en total, y quedan con `early: true` en `catalog.json`.

## Archivos de la skill

- `audio-manifest.example.csv`: 15 filas de ejemplo (no el juego). Copiarlo a `AudioSource/audio-manifest.csv` en la raíz del proyecto y editarlo.
- `generate.mjs`: valida, estima, mide la tarifa, genera. `lib.mjs`: CSV, validación, compuerta de inicio opcional y ledger con bloqueo (lo que prueban los tests). `postprocess.mjs`: ffmpeg y QC. `import_audio.py`: plantilla para el editor.
- Todo lo que se genera va a `AudioSource/audio-work/` (`raw/`, `final/`, `catalog.json`). Fuera de `Content/` y fuera de git.

Columnas del CSV: `id` (letras, números y `_`), `categoria` (una palabra: Mat, Wpn, Amb, UI, Eng, Game), `prompt` (inglés, una frase), `segundos` (0.5 a 30), `loop` (0 o 1), `prompt_influence` (0 a 1, vacío = 0.3), `tomas` (1 a 5). Con `tomas` 2 salen `Id_01` y `Id_02`; el asset será `SW_<Categoria>_<Id>_<NN>`.

## Pasos

1. **Preparar.** Requisitos: Node 20+ y `ffmpeg` en el PATH (`ffmpeg -version`). La clave se toma de la variable `ELEVENLABS_API_KEY` o, si no existe, de `readKey()` del harness (`<HARNESS_DIR>`, cambiable con `HARNESS_DIR`). Nunca leer ni pegar un `.env`.
   ```
   mkdir AudioSource
   copy .claude\skills\elevenlabs-sfx-batch\audio-manifest.example.csv AudioSource\audio-manifest.csv
   ```
2. **Validar y estimar (gratis, sin red).**
   `node .claude/skills/elevenlabs-sfx-batch/generate.mjs AudioSource/audio-manifest.csv --dry`
   Imprime errores por fila, tomas por categoría y el costo a 12 y a 40 créditos por segundo. Saldo gratis: `node scripts/elevenlabs-credits.mjs` desde el harness.
3. **Prueba de 1 s.**
   `node .claude/skills/elevenlabs-sfx-batch/generate.mjs AudioSource/audio-manifest.csv --probe`
   Pide un click de 1 s con `eleven_text_to_sound_v3`, prueba `wav_48000` (si el plan no lo da, cae a `mp3_44100_192`) y mide los créditos por el encabezado o por el saldo (el contador tarda; espera hasta 3 min). Guarda tarifa y formato en `catalog.json`. Si no pudo medir: `... --set-rate N`.
4. **Lote con tope.** Sin tarifa medida o sin `--cap` el script se niega.
   `node .claude/skills/elevenlabs-sfx-batch/generate.mjs AudioSource/audio-manifest.csv --cap 6000 --only Foam,Click`
   - Concurrencia 2 (`--c`), reintento en 429 con `retry-after`, pausa de 1,5 s por llamada.
   - El tope es acumulado del catálogo: la reserva se hace antes de pagar, bajo un archivo de bloqueo (`audio-work/.lock` y `ledger.json`), así que dos procesos a la vez comparten el tope y no se pisan el `catalog.json`. Se detiene con código 2 al pasarse o si el saldo queda bajo. Una reserva de un proceso caído vence a los 30 min.
   - No repite: salta toda toma que ya esté en `catalog.json` o en disco. Si cambias un prompt ya pagado avisa; para repetirlo: `--regen Id` (el archivo viejo va a `raw/_replaced/`, el crédito ya gastado cuenta).
   - Empezar por 1 a 3 filas de cada categoría y escuchar antes de lanzar el resto.
5. **Posprocesar (gratis).**
   `node .claude/skills/elevenlabs-sfx-batch/postprocess.mjs AudioSource/audio-manifest.csv`
   Por toma: WAV 48 kHz (mono; estéreo en Amb y Mus), quita silencio de inicio y cola con 5 y 80 ms de margen, fundidos de 3 y 30 ms, bucles con `acrossfade` de potencia constante (el bucle dura X s menos, X = 20 % hasta 1 s), nivelación y QC. Salida: `final/<Cat>/<Id>_<NN>.wav`, `final/import-list.json`, `final/qc.json`.
   - Niveles por categoría (valores de partida propios del autor, ajustar de oído con Audio Insights): efectos a pico -3 dBFS (UI -6), Amb -28 LUFS, Mus -22, VO -20, todo con pico real máximo -1 dBTP. Cambiar con `--rules reglas.json` (`{"eng":{"peak":-4}}`).
   - Los de menos de 1 s se nivelan por pico: el LUFS no se mide bien en clips cortos.
   - QC marca `danado` (silencio, clipping, hueco, pico real alto, formato) o `revisar`; código de salida 4 si hay dañados. Rehacer: `--force`.
6. **Importar a Unreal (editor cerrado).** Necesita el plugin Python Editor Script habilitado. Con el wrapper de `ue-headless`, que decide por la línea `KIT_OK` (el script la imprime solo si nada falló):
   ```
   $env:AUDIO_FINAL_DIR="C:\ruta\AudioSource\audio-work\final"
   powershell -File .claude/skills/ue-headless/scripts/run-python.ps1 -UERoot "<UE_5.8>" -Project "<Proyecto>.uproject" -Script ".claude/skills/elevenlabs-sfx-batch/import_audio.py"
   ```
   Con el editor abierto: solo desde la consola de Python del editor (`py "C:/ruta/import_audio.py" "C:/ruta/final"`), que la teclea la persona. No por MCP: `execute_tool_script` es un sandbox sin `import unreal`, `os` ni `hashlib`.
   - Importa con `AssetImportTask` y `SoundFactory` a `/Game/Audio/<Cat>/SW_<Cat>_<Id>_<NN>`, nombre fijo y `replace_existing`: reimportar no duplica, y solo reimporta lo que cambió (hash en `import-state.json`).
   - Luego carga el asset con `load_asset` y fija `looping`, `sound_class_object` (`SC_<Cat>`), `attenuation_settings` (`SA_<Cat>`, 3D salvo UI, Mus y VO) y `concurrency_set` (`SCON_<Cat>`, hoy solo Eng con 10 voces y "parar al más lejano").
   - Editar las tablas de arriba del script (atenuación, volumen, concurrencia) a la escala de la mesa de tu juego. Deja `import-report.json` con lo que falló y avisa en el log las propiedades que no existan en esta versión.
7. **Declarar.** `catalog.json` guarda por archivo: prompt, fecha, modelo, formato, plan, créditos y `early`. Alimenta la lista de assets, la casilla de IA de la tienda (itch, Steam) y la bitácora del proyecto.

## Licencias

Estas notas son el resumen del autor de los términos de licencia públicos; revisa los términos vigentes de ElevenLabs antes de apoyarte en ellas.

- Efectos y voz del plan Creator sirven en el juego: "royalty free", comercial, sin atribución. No se puede vender ni licenciar la herramienta ni crear productos competidores.
- Música: solo por la excepción "Indie Game" (menos de USD 500.000 de ingresos del juego y menos de USD 1.000.000 del desarrollador o editor en su último año fiscal). Un "Studio Game" queda fuera. Esta skill no genera música.
- "Uso individual": Creator figura como "For Individual Use Only" y tu equipo es de 2 o más personas. El audio se genera desde una cuenta y queda a nombre de su dueño; no usar la clave de otra persona. Si hay premio o inversión, escribir a soporte de ElevenLabs.
- Lo generado fuera de un plan pago no tiene licencia comercial: confirmar que el plan siga activo y guardar la fecha de cada archivo (ya la guarda el catálogo).
- No subir archivos sueltos (`AudioSource/`, los WAV ni los `.uasset` de audio) a un repositorio o biblioteca públicos (cláusula "Music Library"). El build empaquetado va bien. Poner `AudioSource/` en `.gitignore` y mantener el repo del juego privado.
- Declarar en itch, "Generative AI disclosure": Sound, y Text & Dialog si hay locutor. En un concurso: lista de assets (biblioteca previa, Sonniss, Kenney, CC0) y la bitácora con los prompts.
- No nombrar marcas, bandas sonoras ni artistas en los prompts (regla del proyecto).

## Trampas

- El modelo por defecto de la API sigue siendo v2 (se retira el 1-mar-2027): el script siempre manda `eleven_text_to_sound_v3`.
- Tarifa en conflicto: 40 créditos por segundo (doc oficial) contra 11 a 12 medidos el 1-nov. La prueba de 1 s da un tope prudente, no la pendiente (puede haber mínimo por llamada). Presupuestar con las dos.
- `wav_48000` puede no estar en Creator (MP3 192 kbps sí; WAV 44.1 kHz pide Pro): la prueba cae a `mp3_44100_192` y ffmpeg decodifica. No usar `pcm_*` (sin cabecera).
- `loop` puede ser solo de v2: si v3 lo rechaza (400 o 422) se reintenta sin loop (un fallo no cobra). El bucle lo arma ffmpeg igual; no confiar en la costura del MP3.
- Motores: no generar el motor continuo con IA (el tono deriva). Aquí solo arranques, cortes y texturas, con "steady constant speed, no gear shifts, no pitch changes". El motor se sintetiza (`metasound-engine-family`).
- Prompts en inglés, una frase concreta por sonido, con fuente, entorno y estilo ("close, dry, no music"). `prompt_influence` 0.6 a 0.8 en clics e impactos; 0.3 a 0.4 si se piden 3 tomas.
- Mono para sonidos 3D (criterio propio: es lo habitual para que Unreal los ubique); estéreo solo en ambientes y música de fondo.
- Nunca crear `SoundWave()` nuevo ni Sound Cues por Python: la importación y `load_asset` son el camino.
- Los -16 LUFS y -2 dBTP de video NO sirven para juego.

## Sin verificar

- Tarifa real de v3 en Creator y si `wav_48000` y `loop` funcionan con v3: lo resuelve `--probe`. La doc de la API (leída el 8-nov) lista `wav_48000` y `eleven_text_to_sound_v3` pero no el plan que los permite ni el encabezado `character-cost`.
- Pruebas en `tests/` (`node --test .claude/skills/elevenlabs-sfx-batch/tests/lib.test.mjs .claude/skills/elevenlabs-sfx-batch/tests/generate-fake-server.test.mjs`, 15 pruebas; más `python -I .claude/skills/elevenlabs-sfx-batch/tests/test_import_audio.py`, 3): CSV, tope, fecha y dos lotes a la vez contra un servidor simulado. La API real no se llamó; lo real lo mide `--probe` (1 s).
- `import_audio.py` compila y se probó con un módulo `unreal` falso. Están confirmados en la doc de 5.8 los nombres `looping`, `sound_class_object`, `attenuation_settings`, `concurrency_set` y `MaxConcurrentResolutionRule.STOP_FARTHEST_THEN_OLDEST`. Confirmados en headers de 5.8 (Attenuation.h, SoundAttenuation.h, SoundClass.h, AudioEditor/Classes/Factories): `falloff_distance`, `attenuation_shape_extents`, `attenuate_with_lpf`, `lpf_radius_min/max`, `properties.volume` y los factories `SoundClassFactory`, `SoundAttenuationFactory`, `SoundConcurrencyFactory`. `tests/test_import_audio.py` revisa que imprima `KIT_OK`.
- Los niveles por categoría son criterio propio; la guía de consola es -24 LUFS (±2) con -1 dBTP.
