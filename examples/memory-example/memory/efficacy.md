# Eficacia

| Ronda | Tarea | Pedido vs hecho | Intentos fallidos y por qué | Tiempo | Qué cambiaría |
|---|---|---|---|---|---|
| 6 | Pulido visual (polvo, cuarto, madera, papel, clip) | 8/8 | La luz de relleno sin caída volvió blanca la escena; 3 pasadas con el tinte de la madera (el color del actor pisaba el material) | ~1 h | Medir la escena antes de encuadrar |
| 7 | Nivel de práctica, modo piloto, biblioteca de assets | 5/5 P0 | El editor se cayó al cargar un mapa duplicado; el archivado del build lo bloqueó un exe abierto | ~1 h 50 min | Revisar si hay un exe abierto antes de empaquetar |
| 8 | Guía de Blender + 8 skills del pipeline en un juego real | 1/1 P0, 8/8 skills practicadas | Otra vez el heredoc; la prueba de loseta en 3 pasadas | ~2 h 45 min | Correr las skills en un proyecto real desde el primer día |

## Tendencia (rondas 5 a 7)
- Mejor: el C++ compila a la primera; las pruebas con ganchos cubren un nivel completo en una sola corrida de PIE.
- Se repite: trampas del entorno, no de Unreal (rutas en heredoc, procesos ajenos que retienen archivos).
- Propuesto: agregar "¿está corriendo el exe?" y "Python en un archivo" al preflight (aplicado en la ronda 8).
