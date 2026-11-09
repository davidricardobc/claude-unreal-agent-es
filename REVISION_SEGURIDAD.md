# Revisión de seguridad (9-nov-2026, ronda 9)

Revisión hecha antes de publicar. Después el dueño publicó el repo y un segundo commit corrigió notas y una prueba (ver "Para saber antes de publicar").

## Cómo se limpió el repo

- Todo es una COPIA de una carpeta de trabajo privada, saneada por un script que queda fuera del repo (reglas con expresiones regulares para rutas personales, nombres de personas y nombres de proyectos privados). Las fuentes privadas no se modificaron.
- Las rutas personales y de trabajo pasaron a marcadores: `<AGENT_HOME>`, `<KIT_DIR>`, `<PROJECT_DIR>`, `<HARNESS_DIR>`, `<AUDIO_LIBRARY>`, `<WORK_DIR>`, `<USER>`, `<USER_TEMP>`. Las herramientas leen `UE_ROOT`, `UE_MCP_URL`, `UE_PIE_MAP` y `UE_PROJECT_DIR` del entorno.
- Los nombres de personas se cambiaron por expresiones neutras ("la persona a cargo", "la máquina de prueba"). No hay correos en los archivos.
- Quedaron fuera: dos skills ligadas al plan privado de un equipo para un concurso concreto, la memoria privada del agente y sus notas de sesión, los informes de investigación, el documento de diseño del juego, la biblioteca de assets y los sonidos.
- Se quitó de todas las skills: toda referencia a carpetas de investigación privadas y a informes numerados, las referencias a las dos skills excluidas, los nombres de colaboradores, los roles del equipo y el nombre del concurso. La palabra del nombre de concurso del prefijo antiguo no aparece en ningún archivo (los tokens de los scripts ahora empiezan con `KIT_`).
- La definición del agente es una versión genérica escrita para este repo. La memoria es una plantilla vacía con una guía (`memory-template/README.md`). `examples/memory-example/` es una memoria real del proyecto de práctica, recortada y hecha genérica (sin nombres, sin rutas, sin notas personales). Las lecciones de `examples/` son solo técnicas.
- Se integró la ronda 9 de la fuente privada: skills genéricas (`KIT_*`, compuerta de inicio opcional apagada por defecto, un pawn de referencia, `setup_editor.py`, prueba de loseta en PIE, Movie Render Queue, un script de MetaSound) y una guía de instalación probada. La mezcla se hizo archivo por archivo y se saneó de nuevo con las mismas reglas.
- Traducción: el código, los nombres de archivo, los nombres de skills y los comandos no cambian. Un script de verificación comparó cada script con su fuente (árbol de sintaxis sin docstrings en Python, texto sin comentarios en el resto) y dio 0 diferencias. Las pruebas sin conexión pasan en los dos repos.

## Búsqueda

Comando, desde la raíz del repo, sobre los archivos de texto, luego sobre el historial y luego sobre los binarios. Esa palabra del nombre de concurso se escribe `ja[m]` abajo, para que este archivo no coincida con su propia búsqueda; las corridas reales usaron la palabra normal.

```
grep -rniE 'ricardo|bajonero|celis|@gmail|C:\\\\CODEX|C:\\\\Users|megaja[m]|mega ja[m]|ja[m]|sk-|xi-api-key|[a-f0-9]{32}' .
git log -p -- . ':!REVISION_SEGURIDAD.md' | grep -niE '<el mismo patrón>'
grep -a -iE '<el mismo patrón>' <cada jpg, mp4, uasset, umap>
```

Este archivo se excluye de la búsqueda porque cita el patrón.

| Patrón | Coincidencias | Qué son |
|---|---|---|
| `bajonero` | 4 | Línea de copyright de `LICENSE`, línea de autor del `README.md` y la autoría de los dos commits. Permitido. |
| `ricardo` | 3 | El usuario de GitHub `davidricardobc` en el enlace cruzado del `README.md` y en el correo de autoría de los dos commits. Esperado. |
| `ja[m]` (cubre también las dos formas con mega) | 0 en texto | Un falso positivo en `examples/tableflyer/tableflyer_clip_14s.mp4` (bytes al azar de datos de video). |
| `celis`, `C:\\CODEX`, `C:\\Users`, `@gmail`, `sk-` | 1 línea | Una prueba negativa, `skills/ue-mcp-safe-edit/tests/test_skill.py`, cuya expresión afirma que el texto de la skill NO tiene datos personales. No hay otra coincidencia de texto. `sk-` también tiene un falso positivo en `examples/tableflyer/damage_stages.jpg` (bytes al azar). |
| `xi-api-key` | 2 | Nombre del encabezado HTTP en `skills/elevenlabs-sfx-batch/generate.mjs`. El valor sale de `getKey()`, que lee una variable de entorno y nunca la imprime. |
| `[a-f0-9]{32}` | 0 en texto | En `git log -p` las únicas coincidencias son las dos líneas del ID de commit (40 caracteres hexadecimales), falsos positivos. |

Revisiones extra, todas con 0 coincidencias: formatos de claves reales (`sk_` largo, hexadecimal de 32 o más, `AKIA`, `ghp_`, `xox`, `-----BEGIN`), correos en los archivos, archivos `.env`, `.pem`, `.key` y de credenciales. Una búsqueda de rutas más amplia (`C:[\\/]+(CODEX|Users)`) solo encuentra la misma línea de la prueba. Las únicas otras rutas con letra de unidad son ejemplos genéricos (`C:\Proj`, `C:/intake`, `C:\Program Files\Epic Games\UE_5.8`). Las URL de los archivos son locales (`127.0.0.1`), la base pública de la API de ElevenLabs, tres sitios públicos de assets usados como ejemplo y el enlace cruzado al otro repo. Las imágenes no tienen datos EXIF y el clip solo trae la etiqueta del codificador de ffmpeg.

## Para saber antes de publicar

- Los mensajes de consola de los scripts siguen en español, el idioma original (los textos entre comillas son código y no se tradujeron).
- Después de publicar se corrigieron las notas de "sin verificar" que una sección con fecha de la misma skill ya había confirmado (`trailer-shot-prep`, `ue-render-shots`, `gdd-to-datatables`, `build-tile`, `flight-test-pilot`, `metasound-engine-family`, `package-and-verify-build`), y se arregló una cadena de prueba con una letra mal codificada. Lo que sigue marcado "sin verificar" de verdad no se probó.
- `elevenlabs-sfx-batch` tiene una compuerta de inicio opcional (`KIT_START`) apagada por defecto.
- `asset-intake` trae reglas de licencia de Synty, que son públicas (no redistribuir, no subir a IA 3D). No se incluye ningún archivo de Synty.
- Los renders y el clip son del proyecto de práctica TableFlyer (contenido propio).
