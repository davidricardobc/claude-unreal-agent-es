---
name: ue-render-shots
description: Saca renders de presentación de modelos o escenas en Unreal Engine 5.8 para mostrar en una reunión - foto bonita en 3/4 (hero), lineup de varios modelos, turntable de N ángulos, primeros planos y tomas de acción, a 1920x1080 o más, con hoja de contacto y, si se pide, un clip corto. Usa CaptureViewport del MCP de Epic con la cámara calculada por toma, y para alta resolución HighResShot desde la consola del editor. Úsala cuando digan "hazme un render", "imagen del modelo", "foto bonita del avión", "lineup de los modelos", "turntable", "imágenes para la reunión", "render para presentar", "clip corto del modelo", "beauty shot", "product shot", "render the model". No es para revisar cambios (eso es ue-viewport-eyes) ni para el tráiler (trailer-shot-prep).
---

# ue-render-shots

Imágenes limpias para mostrar, no para revisar. Solo mueve la cámara y captura; si hace falta poner luz, fondo o una cámara, eso es escribir y sigue `ue-mcp-safe-edit`.

| Skill | Para qué | Resolución |
|---|---|---|
| `ue-viewport-eyes` | revisar lo hecho, montaje barato en tokens | la del viewport, reducida a 1280x720 |
| `ue-render-shots` (esta) | presentar: hero, lineup, turntable, acción | 1920x1080 o más |
| `trailer-shot-prep` | tráiler de 30 a 60 s con Movie Render Queue | 1920x1080, 60 fps |

## Antes de empezar

1. `ue-session-preflight` en VERDE (editor abierto con GPU, no `-nullrhi`; sin PIE).
2. Scripts en `.claude/skills/ue-render-shots/scripts/`: `render_plan.py` (puro), `render_shots.py` (MCP), `editor_highres.py` (consola de Python del editor). Ejemplo: `templates/subjects.example.json`. Reusa el cliente MCP de `ue-viewport-eyes/scripts/ue_capture.py`. Puerto por `UE_MCP_URL`.
3. Carpeta de salida: `Saved/Renders/<AAAAMMDD-HHMM>_<tema>/` (fuera de git).

## Pasos

1. **Qué se quiere mostrar.** Escribir 2 o 3 frases: qué modelos, para quién, qué debe notarse (forma, color, escala). Elegir tomas: `hero` (3/4 frontal, la foto bonita), `turntable:N` (N ángulos alrededor), `lineup` (todos juntos de frente), `closeups` (uno por modelo) y tomas de acción a mano (`{"name", "loc", "rot"}`).
2. **Sujetos.** Centro y radio de cada actor por MCP (`ActorTools.get_actor_bounds`):
   `python .claude/skills/ue-render-shots/scripts/render_shots.py bounds <ruta_actor> [...] --out <dir>/subjects.json`
   La ruta es la del objeto en el nivel (`/Game/Maps/X.X:PersistentLevel.<Actor>`; sale de `SceneTools.find_actors`). Editar `shots` en el JSON.
3. **Plan:** `python .claude/skills/ue-render-shots/scripts/render_plan.py <dir>/subjects.json --out <dir>/plan.json`. Calcula para cada toma la distancia que encuadra al sujeto con margen (FOV horizontal 90 y 16:9 por defecto) y la rotación que lo mira. Termina en `PLAN_OK` o `PLAN_FAIL <motivo>`.
4. **Luz y fondo (opcional, es escribir).** Para una foto bonita: nivel limpio duplicando `/Engine/Maps/Templates/Template_Default` (`AssetTools.duplicate`) y la luz exterior por defecto (skill `default_outdoor_lighting` del toolset de Epic). Los modelos se colocan en ese nivel. Pedir el sí antes de crear assets.
5. **Capturar (camino rápido, MCP):**
   `python .claude/skills/ue-render-shots/scripts/render_shots.py capture <dir>/plan.json --out <dir> --min 1920x1080`
   Una `CaptureViewport` por toma, con su `captureTransform`, sin rejilla ni etiquetas y sin gizmos. Escribe `<toma>.png` y `manifest.json`. Fin: `RENDER_OK`, `RENDER_LOWRES` (código 3) o `RENDER_FAIL`.
   `CaptureViewport` da el tamaño del viewport, que cambia con la ventana (1912x862 o 1304x584 en la máquina de prueba). Con `RENDER_LOWRES`: pasar al paso 6 (lo normal para presentar) o pedir maximizar el viewport (F11) y repetir. No usar `CaptureEditorImage` para presentar: captura todo el escritorio (1280x313 con dos monitores).
6. **Alta resolución (HighResShot):** el MCP no trae herramienta de consola, así que una línea la teclea la persona.
   `python .claude/skills/ue-render-shots/scripts/render_shots.py highres <dir>/plan.json --out <dir> --res 2560x1440`
   Imprime la línea para la consola de Python del editor (`py ".../editor_highres.py" ".../highres-jobs.json"`). Antes: Game View (tecla `G`) para que no salgan íconos ni cajas de triggers. El script mueve la cámara por toma, espera, dispara `HighResShot WxH filename=<png>` y espera el PNG. Fin en el Output Log: `RENDER_HIGHRES_OK` o `RENDER_HIGHRES_FAIL <tomas>`.
7. **Revisar con visión** cada imagen a 800 px de ancho como máximo: sujeto completo y centrado, sin material por defecto, sin íconos ni gizmos, luz que deja ver la forma. Repetir solo la toma mala (editar su `loc`/`rot` en el plan).
8. **Hoja de contacto** para la reunión:
   `powershell -File .claude/skills/ue-viewport-eyes/scripts/shrink-montage.ps1 -Images <png1>,<png2>,... -OutFile <dir>/contact.jpg -Cell 960 -Columns 2`
9. **Entregar:** carpeta, lista de imágenes con su tamaño (de `manifest.json`) y la hoja de contacto. No se publica nada: compartir lo hace la persona.

## Clip corto (opcional)

Sin Movie Render Queue frágil: se reusa `trailer-shot-prep`, que crea la secuencia sin Sequencer abierto y renderiza por línea de comandos con el editor cerrado.
1. CSV de una o dos filas (`moment,duration_s,camera_type,map,target`), por ejemplo `turntable,8,orbit,/Game/Maps/X,<etiqueta del actor>`.
2. `python .claude/skills/trailer-shot-prep/scripts/shot_plan.py check clip.csv --min-s 5 --max-s 20`.
3. Seguir los pasos 3 a 7 de `trailer-shot-prep` con `KIT_TRAILER_MIN_S=5` y `KIT_TRAILER_MAX_S=20`.
Estado: sin verificar en la máquina (ver abajo). Si falla, la alternativa es grabar la pantalla del turntable en PIE.

## Regla de distancia de cámara (verificada, rondas 3 a 7 de TableFlyer)

- Antes de la primera toma, medir el tamaño REAL del sujeto (`get_actor_bounds`) y de la escena (bordes de la mesa, de dónde entra la luz). Varias tandas salieron con el sujeto como un punto por no hacerlo.
- Distancia para que el sujeto llene una fracción `f` del ancho: `d = (tamaño / f) / (2 * tan(FOV_h / 2))`. Con FOV 60 y f = 0,5, un avión de 2 m va a ~3,5 m. En un mundo a escala 100x (mesa de 400 m) los aviones miden 1,6 a 2,6 m: cámara a 3-8 m, no a 40.
- Un plano de papel visto de canto casi desaparece: subir la cámara 10-20° o escalar el modelo de vitrina.
- Sin ventana (alguien usa el PC): gancho C++ en el pawn que corre `HighResShot WxH filename=X` en PIE más una cámara libre movida por propiedades Debug; o `FScreenshotRequest::RequestScreenshot` para capturas con HUD.
- Clips: grabar cuadro por cuadro desde el motor (`FApp::SetUseFixedTimeStep` + `SetFixedDeltaTime(1/30)` + un `RequestScreenshot` por tick) y unir con ffmpeg. Grabar la pantalla falla si otra ventana queda encima. Verificado (30 fps exactos, ~3 cuadros/s reales).

## Trampas

- Tomas en juego (con HUD o efectos): `HighResShot` en PIE, o el gancho C++ `FScreenshotRequest::RequestScreenshot` descrito en `ue-viewport-eyes`; no `CaptureEditorImage`.
- `CaptureViewport` exige `captureTransform` y `annotations` aunque digan opcionales; el script los manda siempre.
- `bShowUI=false` quita gizmos pero no las cajas de triggers ni los visualizadores de componentes: para fotos limpias, Game View y el camino de alta resolución.
- Texturas borrosas en la primera toma: streaming de mips. El camino de alta resolución espera unos cuadros por toma; en el rápido, repetir la toma.
- `execute_tool_script` no sirve para esto (sandbox sin `import unreal`) y `ue-headless/run-python.ps1` corre sin GPU.
- GPU de 6 GB: `HighResShot` por encima de 3840x2160 puede fallar por memoria; subir de a poco.

## Pruebas de la skill

`python -I .claude/skills/ue-render-shots/tests/test_render_shots.py` (14 pruebas, sin Unreal): plan y encuadre, veredicto de resolución, comando `HighResShot`, máquina de estados de `editor_highres.py` y `capture`/`bounds` contra un servidor MCP falso.

## Sin verificar (cada uno en 1 a 2 minutos)

- El argumento de actor de `get_actor_bounds` (`{"refPath": ruta}`) y la forma del `Box` que devuelve. Verificar: `describe_toolset editor_toolset.toolsets.actor.ActorTools` y un `bounds` con un actor.
- El ciclo completo de `editor_highres.py` y que `py "<script>" "<json>"` pase el argumento a `sys.argv`. Verificar con un plan de 1 toma: debe salir el PNG con el tamaño pedido.
- Que `HighResShot` en el viewport del editor respete Game View. Verificar con una toma con un trigger a la vista.
- El clip: `render-shots.ps1` de `trailer-shot-prep` no se ha corrido en la máquina. Verificar con una toma de 5 s.

API verificada en headers de 5.8: `EditorAppToolset.h` (CaptureViewport, sin herramienta de consola), `UnrealEditorSubsystem.h` (set_level_viewport_camera_info), `KismetSystemLibrary.h` (ExecuteConsoleCommand), `UnrealClient.cpp` (`HighResShot WxH filename=`), `actor.py` (get_actor_bounds), `PySlate.cpp` (register_slate_post_tick_callback).
