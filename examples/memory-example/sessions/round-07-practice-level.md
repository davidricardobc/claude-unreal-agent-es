# Ronda 7 · Nivel de práctica y biblioteca de assets

Pedido: un nivel de práctica de vuelo libre (sin daño, obstáculos, campo de tiro, cambio de avión, modo piloto opcional con loops), una biblioteca de assets, un hangar. Exe empaquetado con sonido.

## Hecho
- Clases `TFPractice`: blancos de tiro que caen y se levantan, aros con campana en carreras ordenadas, un hangar de aviones giratorios (volar por un puesto cambia el avión).
- Pawn: modo práctica por el nombre del mapa, L cambia de nivel, F activa el modo piloto (cuaterniones, loop verificado en el log).
- Mapa de práctica armado con un script re-ejecutable; biblioteca de assets copiada con las mismas rutas /Game.
- El empaquetado salió bien, pero la carpeta del build estaba bloqueada por el juego abierto: se copió el build en staged a una carpeta nueva.

## Pendiente
- La persona prueba el modo piloto (¿da mareo?).

## Aprendido
- Duplicar un mapa y cargarlo en llamadas separadas. Un build en staged es un build utilizable si falla el archivado. Un gancho de teletransporte vuelve rápidas las pruebas por zona.
