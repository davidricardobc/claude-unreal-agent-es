---
name: ue-viewport-eyes
description: Da ojos al agente en Unreal Engine 5.8. Toma capturas desde 4 ángulos con CaptureViewport del MCP de Epic (en PIE con CaptureEditorImage), las reduce y las junta en un montaje para gastar pocos tokens, las revisa con visión contra lo que se pidió, las compara con la captura anterior y entrega un reporte corto. Úsala después de cambios de nivel, material, luz o cámara, y al armar cada pieza o módulo del nivel. Frases disparadoras - "mira cómo quedó", "toma capturas del nivel", "revisa el viewport", "compara con la captura anterior", "se ve bien?", "verifica visualmente", "take screenshots", "check how it looks", "compare with the previous capture", "visual check of the level".
---

# ue-viewport-eyes

Revisar con la vista lo que se hizo por MCP, sin gastar el contexto en imágenes grandes. Una captura bien escogida vale más que diez. Esta skill solo mueve la cámara y captura; no edita assets.

## Cuándo usarla

- Tras cambiar nivel, material, iluminación, cámara o HUD.
- Al terminar cada pieza o módulo del nivel, antes de pasar a la siguiente.
- Cuando la persona pide "mira cómo quedó" o hay que comparar con una versión anterior.

## Pasos

1. **Preparar.** Correr (o haber corrido) `ue-session-preflight`. Guardar solo el paquete tocado. Si hay Niagara o MetaSound, guardar antes de entrar en PIE: un fallo borra lo no guardado.
2. **Escoger el modo.**
   - Cámara del editor: geometría, layout, escala, luces estáticas. Rápido.
   - PIE: efectos, partículas, HUD, materiales dinámicos, cámara de juego. Los efectos no se verifican en el editor.
3. **Escribir lo pedido en 3 a 5 criterios verificables** antes de mirar (por ejemplo "el módulo cierra con el vecino", "sin huecos", "escala de una puerta de 2 m"). Sin criterios, la revisión se vuelve un "se ve bonito".
4. **Herramientas (verificadas en 5.8).** Toolset `EditorToolset.EditorAppToolset` por la metaherramienta `call_tool` (`toolset_name`, `tool_name`, `arguments`):
   - `CaptureViewport(captureTransform, annotations, bShowUI=false)`: PNG base64 del viewport del editor. Pedir siempre `captureTransform` y `annotations` (en la práctica los exige aunque digan opcionales). `annotations` con todo en 0 = foto limpia; con rejilla y etiquetas solo si hace falta ubicar cosas. `bShowUI=false` oculta gizmos y selección.
   - `CaptureEditorImage()`: la ventana completa del editor. En PIE es la que trae el HUD.
   - `IsPIERunning`, `StartPIE` (`options.playMode=PlayMode_InViewPort`, `warmupSeconds`) y `StopPIE`.
   - `GetCameraTransform` / `SetCameraTransform` / `FocusOnActors` (este último no sirve con PIE activo).
   La resolución es la del viewport y cambia con el tamaño de la ventana (en la máquina de prueba salió 1912x862 un día y 1304x584 otro); no se puede pedir otra por MCP. Revisar el tamaño de cada PNG. Para imágenes de presentación a 1920x1080 o más usar `ue-render-shots`.
   - `CaptureEditorImage` captura TODO el escritorio: con dos monitores salió 1280x313, ilegible (verificado). Para tomas con HUD legibles, capturar desde el juego: `HighResShot` en PIE o un gancho C++ de depuración en el pawn (`FString DebugScreenshotName` que llama `FScreenshotRequest::RequestScreenshot(FPaths::ProjectSavedDir()/"Capturas"/Nombre.png, true, false)` y que el agente activa con `set_properties`; verificado, guarda 1322x804).
5. **Cuatro ángulos** alrededor del centro `C` del objetivo, con `R` = media diagonal de su caja (cm) y distancia `d` = 1,8 x R. Posición = `C + d * (cos(el)*cos(az), cos(el)*sin(az), sin(el))`; mirando a `C`: `yaw = az + 180`, `pitch = -el`. Ajustar si algo queda fuera de cuadro.

| Nombre | az | el | Para ver |
|---|---|---|---|
| `front` | 0 | 15 | silueta, simetría |
| `tq` | 45 | 35 | volumen, cortes |
| `side` | 90 | 10 | alturas, perfil |
| `top` | 0 | 80 | layout, huecos, cierres |

6. **Íconos del editor.** `bShowUI=false` quita gizmos y contornos, pero las cajas de triggers y otros visualizadores de componentes siguen saliendo (verificado). Para una foto limpia: PIE + `CaptureEditorImage`, o pedirle a la persona Game View (tecla `G`).
7. **Capturar** los 4 en `Saved/Eyes/<AAAAMMDD-HHMM>_<etiqueta>/` con el script (calcula las poses del paso 5, llama `CaptureViewport` y escribe `front.png`, `tq.png`, `side.png`, `top.png` y `cams.json`):
   `python .claude/skills/ue-viewport-eyes/scripts/ue_capture.py orbit --out <dir> --center X,Y,Z --radius R`
   Una toma suelta: `... one --out <dir>/x.png --loc X,Y,Z --rot PITCH,YAW`. En PIE: `... editor --out <dir>/pie.png`. Puerto por `UE_MCP_URL` (por defecto `http://127.0.0.1:8123/mcp`). `Saved/` no entra a git. Si las texturas salen borrosas, esperar un par de segundos y repetir: puede ser el streaming de mips.
8. **Reducir y juntar** (una sola imagen cuesta menos que cuatro):
   `powershell -File .claude/skills/ue-viewport-eyes/scripts/shrink-montage.ps1 -Images <dir>\front.png,<dir>\tq.png,<dir>\side.png,<dir>\top.png -OutFile <dir>\montage.jpg`
   Da un JPEG de 1280x720 (unos 1.230 tokens, regla: ancho x alto / 750). Para ver un detalle, capturar de nuevo ese ángulo cerca y leerlo solo, a 800 px de ancho como máximo.
9. **Revisar con visión** el montaje (`Read` de la imagen). Por cada criterio: cumple, no cumple o no se ve. Buscar además: objetos flotando o cortados, z-fighting, material por defecto (cuadrícula gris), luz negra o sobreexpuesta, escala rara, huecos, íconos.
10. **Comparar con la anterior.** Mismas coordenadas de cámara (`cams.json` previo) y misma resolución. Juntar antes y después:
    `powershell -File .claude/skills/ue-viewport-eyes/scripts/shrink-montage.ps1 -Images <anterior>\montage.jpg,<nueva>\montage.jpg -OutFile <nueva>\cmp.jpg -Cell 960 -Columns 1 -Labels antes,despues`
    Reportar qué cambió y, sobre todo, qué cambió sin que se pidiera.
11. **Cerrar PIE** si se abrió. No guardar el mapa solo por haber movido la cámara.
12. **Reporte** (máximo 8 líneas):

```
Veredicto : OK / CON OBSERVACIONES / NO CUMPLE
Criterios : 1 cumple, 2 cumple, 3 NO (hueco entre módulo A y B, vista top)
Cambios   : respecto a 20261113-1020: techo más alto (pedido); sombra nueva en lado este (no pedida)
Dudas     : lo que la imagen no permite afirmar (por ejemplo efecto de humo, solo en PIE)
Capturas  : Saved/Eyes/20261113-1140_modulo3/
```

## Trampas

- **Íconos en vez de render real.** Las capturas del editor muestran sprites de luces y emisores que parecen partículas (trampa conocida de `ibrews/ue5-mcp`). Un efecto se verifica en PIE, no en el editor.
- Después de cambios grandes el flujo que sí se cuenta es: PIE, captura, comparar (fuente secundaria).
- El HUD no sale en `CaptureViewport`. `CaptureEditorImage` lo trae pero con varios monitores queda diminuto: preferir la captura disparada desde el juego (paso 4).
- Captura negra o vacía: viewport minimizado o sin foco, o PIE aún cargando. Esperar y repetir una vez; si sigue, avisar.
- Editor con `-nullrhi` (sirve para el MCP sin ventana): no dibuja, así que no hay capturas útiles. Las capturas necesitan el editor con GPU.
- GPU modesta: PIE pesado. Capturar con calidad media y no dejar PIE abierto entre pruebas. Datos de la máquina en `references/maquina.md`.
- Mover la cámara es estado del editor, no de assets, pero sigue la regla de un solo escritor por editor (`ue-mcp-safe-edit`).
- Opcional si está instalado: VibeUE trae escenarios asíncronos de PIE con cierre garantizado.

## Sin herramienta de capturas

Ya no hay plan B en Python por MCP: `ProgrammaticToolset.execute_tool_script` es un sandbox (solo `json`, `math`, `re`, `time`, `datetime`, `copy` y `execute_tool`), sin `import unreal`. Y `ue-headless/run-python.ps1` aborta con el editor abierto y corre sin GPU. Si `CaptureViewport` falla dos veces: pedirle a la persona la captura (o `HighResShot` en la consola del editor) y avisar.

## Pruebas

`python -I -m unittest discover -s .claude/skills/ue-viewport-eyes/tests` (14 pruebas, Windows PowerShell, sin Unreal). `test_ue_capture.py` prueba las poses, los argumentos, la lectura del PNG y el cliente contra un servidor MCP falso en localhost. `shrink-montage.ps1` sale con código 1 y mensaje `FALTA <ruta>` en stderr si una imagen no existe o no se puede leer, y con 2 si no se pasa ninguna.

## Sin verificar (confirmar el día 1)

- `CaptureViewport` sin `captureTransform` (usar la cámara actual): el script siempre lo manda; si se necesita, probar una vez con `describe_toolset EditorToolset.EditorAppToolset` (1 minuto).
- Si Game View se puede activar por MCP (no aparece en `EditorAppToolset.h`); por ahora se pide a la persona.
