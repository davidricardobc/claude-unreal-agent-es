# Plantilla de memoria

Copia `memory/` y `sessions/` en la casa del agente (una carpeta a tu elección, de preferencia un repo git local). El agente los lee al empezar cada conversación y los actualiza al terminar. Un ejemplo ya lleno, hecho a partir de un proyecto real, está en [`../examples/memory-example/`](../examples/memory-example/).

## Qué va en cada archivo

| Archivo | Qué escribir | Cuándo |
|---|---|---|
| `memory/MEMORY.md` | Una línea por archivo: nombre y qué contiene. Nada más. | Cuando se agrega o se quita un archivo |
| `memory/current-project.md` | Objetivo, hitos hechos, pendientes, dónde está el build. En presente, siempre al día. | En cada sesión que cambie el estado |
| `memory/lessons.md` | Algo que funcionó o falló, y cómo lo sabes (compilación, línea de log, captura, número). | Cuando una lección se verifica |
| `memory/errors.md` | El mensaje de error exacto, la causa y el arreglo. | Cuando se resuelve un error |
| `memory/decisions.md` | Una elección entre opciones y por qué. | Cuando se toma una decisión |
| `memory/preferences.md` | Cómo le gusta trabajar a tu persona: idioma, largo de los reportes, qué necesita un sí. | Cuando corrige al agente |
| `memory/efficacy.md` | Una fila por sesión: pedido vs hecho, intentos fallidos y por qué, tiempo, qué cambiar. | Al final de cada sesión |
| `sessions/AAAA-MM-DD-tema.md` | Unas 30 líneas: lo pedido, lo hecho, lo pendiente y dónde, lo aprendido. | Al final de cada sesión |

## Reglas que la mantienen útil

1. **Evidencia o etiqueta.** Cada lección termina diciendo cómo se verificó. Si no se probó, escribe "sin verificar". Una memoria llena de suposiciones es peor que ninguna.
2. **Errores exactos.** Copia el mensaje tal como se imprimió (es lo que vas a buscar con grep la próxima vez), luego la causa y luego el arreglo.
3. **Actualiza, no dupliques.** Si una lección ya existe, edítala. Si resultó falsa, corrígela o bórrala y dilo.
4. **Reglas accionables arriba.** `lessons.md` empieza con una lista corta y numerada de reglas destiladas del registro de abajo. Esa lista es lo primero que lee el agente.
5. **Consolida.** Cuando un archivo pase de unas 300 líneas, mueve la parte vieja a `memory/archive-AAAA-MM.md` con un resumen de 10 líneas y mantén la lista de reglas al día.
6. **Promueve los patrones.** Un procedimiento que se repite 2 o más veces se vuelve skill (o un cambio a una). La memoria guarda la experiencia; las skills guardan el procedimiento.
7. **Revisa la tendencia.** Cada 3 sesiones, lee las últimas 3 filas de eficacia y propón 1 o 2 cambios al flujo de trabajo, a las skills o a la definición del agente. Propón, no apliques solo.
8. **Nunca guardes secretos ni datos personales.** Nada de claves, tokens, contenido de `.env`, correos ni notas privadas sobre personas.
9. **Commit local** al final de cada sesión con rutas explícitas (`git add memory sessions tools`), nunca `-am`.
