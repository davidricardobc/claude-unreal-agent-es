---
name: trailer-shot-prep
description: Prepara el tráiler de un juego en Unreal Engine 5.8 a partir de una lista de momentos (CSV con momento, duración, tipo de cámara y mapa). Valida la lista, crea un Level Sequence con CineCamera por toma con Python de editor, crea el preset de Movie Render Queue (1920x1080 o más, 60 fps, secuencia PNG o EXR para editar), da el comando de render por línea de comandos, arma el ensamblado con ffmpeg, verifica el video final con ffprobe y trae una checklist de tráiler (30 a 60 s por defecto, gancho en 3 s, apto para todo público). Úsala para preparar y renderizar las tomas del tráiler y medir el archivo resultante; no es la revisión de una entrega final a un concurso o tienda (esa revisión puede llamar a `verify_video.py`). Frases disparadoras - "prepara el tráiler", "shot list", "toma de héroe", "render del tráiler", "revisa el video final", "trailer shots", "movie render queue", "verify the trailer".
---

# trailer-shot-prep

De una lista de momentos a tomas renderizadas y un video verificado. Genérica: sirve para el tráiler de cualquier juego. La skill no inventa contenido: los momentos los elige un humano y salen de juego real.

## Piezas (en `.claude/skills/trailer-shot-prep/`)

| Archivo | Para qué | Corre en |
|---|---|---|
| `templates/shots.example.csv` | Shot list de ejemplo ficticia (9 tomas, 41,5 s) | datos |
| `scripts/shot_plan.py` | Valida el CSV, cámaras por clave, manifest, comandos ffmpeg | Python puro |
| `scripts/build_sequences.py` | Un Level Sequence + CineCamera spawnable por toma | dentro de UE |
| `scripts/make_mrq_preset.py` | Preset de MRQ: 1920x1080 mínimo, 60 fps, PNG/EXR | dentro de UE |
| `scripts/render-shots.ps1` | Renderiza cada toma por línea de comandos (`-DryRun` imprime) | Windows |
| `scripts/verify_video.py` | Resolución, fps y duración con ffprobe | Python puro |
| `tests/test_trailer_shot_prep.py` | 21 pruebas sin Unreal | Python puro |

## Antes: activar Movie Render Queue

El render usa Movie Render Queue, que no viene activo en un proyecto nuevo. Una vez por proyecto:
1. En el `.uproject`, dentro de `"Plugins"`, agregar `{"Name": "MovieRenderPipeline", "Enabled": true}` (o en el editor: Edit > Plugins > "Movie Render Queue" > Enabled).
2. Cerrar y volver a abrir el editor. En un proyecto C++, compilar el target del editor si el editor lo pide.
3. Comprobar: `make_mrq_preset.py` debe terminar en `KIT_OK`. Si dice `KIT_FAIL no hay clase de config de MRQ`, el plugin no quedó activo.

## Flujo

1. **Shot list.** Copiar `templates/shots.example.csv` y editar. Columnas: `moment,duration_s,camera_type,map[,target][,notes]`. Tipos de cámara: `static`, `orbit`, `dolly`, `crane`. `target` es la etiqueta del actor que se mira (si falta, se mira al origen). Escoge un humano; solo juego real.
2. **Validar:** `python scripts/shot_plan.py check shots.csv`. Falla si el total no está entre 30 y 60 s (valores por defecto; otro proyecto usa `--min-s` y `--max-s`), si hay tipos o nombres malos o si el mapa no es una ruta `/Game/...`. Avisa si la primera toma pasa de 3 s.
3. **Secuencias** (editor cerrado, ver `ue-headless`): `KIT_TRAILER_SHOTS=<csv>` y `run-python.ps1 -Script .../build_sequences.py`. Crea `/Game/Cine/Trailer/LS_<NN>_<momento>` a 60 fps. La cámara se crea con `seq.add_spawnable_from_class` (deprecada en 5.5 pero vigente en 5.8): la versión del `LevelSequenceEditorSubsystem` exige la secuencia abierta en Sequencer y sin editor devuelve un binding vacío. El script valida el binding y dice qué camino usó (`KIT_INFO camara por ...`). Idempotente (`KIT_TRAILER_REBUILD=1` recrea); cada mapa se carga una vez. Después, un humano revisa cada toma con `ue-viewport-eyes` y ajusta cámaras en el Sequencer.
4. **Preset:** `run-python.ps1 -Script .../make_mrq_preset.py` crea `/Game/Cine/Presets/TrailerHD60`. Variables: `KIT_TRAILER_FORMAT` (png, exr, prores), `KIT_TRAILER_TEMPORAL` (8; 4 con 6 GB de VRAM), `KIT_TRAILER_OUT`. Nunca baja de 1920x1080.
5. **Render:** `python scripts/shot_plan.py manifest shots.csv manifest.csv --out-dir <carpeta>` (la misma carpeta que `KIT_TRAILER_OUT` del preset), luego `render-shots.ps1 -UERoot ... -Project ... -Manifest manifest.csv -DryRun` y quitar `-DryRun`. Equivale a `UnrealEditor-Cmd.exe <uproject> <mapa> -game -LevelSequence=<seq> -MoviePipelineConfig=<preset> -windowed -resx=1920 -resy=1080 -log -notexturestreaming`. Los fotogramas viejos de la toma se mueven a `old\` antes de renderizar y el éxito se decide contando solo los `.png`/`.exr` nuevos, no por el código de salida. Con GPU de 6 GB, bajar Lumen con `KIT_TRAILER_CVARS` al crear el preset (nombres de cvar por comprobar) y renderizar una toma de prueba primero.
6. **Ensamblar:** `python scripts/shot_plan.py ffmpeg shots.csv <OutDir>` imprime los comandos (PNG a MP4 H.264 por toma, luego unir). Añadir música y títulos en el editor de video.
7. **Verificar:** `python scripts/verify_video.py trailer.mp4`. Falla por debajo de 1920x1080, de 30 fps o fuera de 30 a 60 s; avisa si es menos de 60 fps o no hay audio. Sin ffprobe da código 3 y no cuenta como "pasó" (`winget install Gyan.FFmpeg`).
8. **Checklist** (abajo) y mostrar el resultado a la persona. No subir nada: publicar lo hace un humano.

## Checklist de tráiler

- [ ] Duración entre 30 y 60 s (medida con `verify_video.py`).
- [ ] Resolución 1920x1080 o más; 60 fps ideal.
- [ ] Gancho en los 3 primeros segundos: acción o imagen fuerte, sin logo ni pantalla negra al inicio.
- [ ] Gameplay real en los primeros 5 s. Nada de mock-ups ni imágenes que no sean del juego.
- [ ] Todo el texto en pantalla, subtítulos y voz en el idioma que exija el concurso (por ejemplo, inglés).
- [ ] Apto Teen: sin sangre, sin desnudos, sin lenguaje fuerte, sin símbolos de odio.
- [ ] Sin marcas ni logos de terceros; música y sonido con licencia o propios, anotados en la lista de assets.
- [ ] Título y nombre del juego legibles al menos 2 s; tarjeta final con nombre y dónde jugarlo.
- [ ] Audio parejo (sin picos ni silencios raros) y legible en altavoces de laptop.
- [ ] Ritmo: tomas de 2 a 6 s en el medio; sin más de 2 tomas largas (> 8 s).
- [ ] Probado en un reproductor externo, no solo en el editor de video.
- [ ] Si es para un concurso o tienda: sus reglas leídas en la página oficial (el resumen de la comunidad no es la fuente).

## Trampas

- MRQ solo acepta pocos argumentos por línea de comandos; lo demás va en el preset o por Python (`MoviePipelinePythonHostExecutor`).
- Un render por toma en serie: si una falla, las demás siguen y el script reporta `RENDER_FAIL (n)`.
- Las cámaras creadas por claves son un punto de partida. El ojo humano decide la toma.
- Física o gameplay en vivo no son deterministas bajo MRQ. Para momentos de juego, mejor grabar un replay o capturar con OBS y usar esta skill para las tomas de cámara.
- Anti-aliasing temporal alto con 6 GB de VRAM puede reventar la memoria: bajar `KIT_TRAILER_TEMPORAL`.

## Estado (verificado el 9-nov-2026, UE 5.8.4)

- De punta a punta en un proyecto C++ en blanco con Movie Render Queue activo: `shot_plan.py check` -> `build_sequences.py` (2 secuencias) -> `make_mrq_preset.py` -> `shot_plan.py manifest` -> `render-shots.ps1` (editor cerrado; 240 PNG 1920x1080 en ~2 min) -> ffmpeg -> `verify_video.py` (`VIDEO_OK`, 1920x1080, 60 fps).
- Confirmado: el patrón `{sequence_name}.{frame_number}` da `LS_01_x.0000.png`; la resolución del preset manda; `-game -LevelSequence` renderiza sin abrir el editor completo.
- Arreglado: `get_channels()` ya no existe en 5.8.4; se usa `get_all_channels()`.
- Las cámaras son automáticas (orbit, dolly, crane, static alrededor del objetivo): sirven de borrador; un humano las ajusta en el Sequencer.
- `KIT_TRAILER_RADIUS` es uno solo para todas las tomas (pendiente: radio por toma en el CSV).

## Verificado en TableFlyer (ronda 8, 9-nov-2026, UE 5.8.4)

- `shot_plan.py check` y `build_sequences.py` corrieron con un juego real: 6 secuencias en `/Game/Cine/Trailer` (`KIT_OK`).
- Arreglado: `MovieScene3DTransformSection.get_channels()` ya no existe en 5.8.4; ahora `get_all_channels()`.
- Antes de todo: el plugin **Movie Render Queue** debe estar activo (ver "Antes: activar Movie Render Queue"). En TableFlyer no lo estaba; en el proyecto en blanco se activó y el render funcionó.
- `KIT_TRAILER_RADIUS` es uno solo para todas las tomas: en un mundo a escala 100x un hangar de 90 m y un pedestal de 10 m piden radios distintos (pendiente: radio por toma en el CSV).
