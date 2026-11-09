---
name: build-tile
description: Arma una loseta o segmento de nivel modular en Unreal Engine 5.8 como Level Instance. Define rejilla y tamaño estándar, bordes que encajan, valida un manifiesto JSON de la loseta, coloca props con Python de editor, hornea el PCG en el editor (el PCG en runtime ignora el transform del Level Instance), prueba el giro 0/90/180/270 (bordes y colisión), revisa el presupuesto de rendimiento para una GPU de 6 GB, usa luz dinámica y captura con ue-viewport-eyes. Frases disparadoras - "arma una loseta", "nueva loseta del nivel", "valida el manifiesto de la loseta", "prueba el giro de la loseta", "presupuesto de la loseta", "build a level tile", "modular level segment", "tile rotation test", "bake PCG for the tile".
---

# build-tile

Una loseta es un nivel pequeño (Level Instance) que encaja con otras por sus bordes y se puede girar de 90 en 90 grados. Se arma desde un manifiesto JSON que se valida antes de tocar Unreal. Todo lo de abajo es genérico: las cifras son propuestas a medir.

## Antes de empezar

1. Correr `ue-session-preflight`. Leer `ue-mcp-safe-edit` si se escribe por MCP (leer, escribir, releer).
2. Plantillas en `.claude/skills/build-tile/scripts/`: `validate_tile_manifest.py` (puro), `place_tile.py` (idempotente: limpia sus props antes), `bake_pcg.py` y `rotation_smoke_test.py` (Python de editor), `api_probe.py` + `api.txt` (sonda de API), `tile_manifest.example.json`.
   Día 1: correr `api_probe.py` con `run-python.ps1`; dice en 1 minuto qué llamadas `unreal.*` faltan y si cada una es función (`func`, se llama con `()`) o propiedad (`prop`, va con `get/set_editor_property`). Usa la sonda compartida de `ue-headless`.
3. Correr los scripts de editor con `ue-headless` (`run-python.ps1`). Pasan el manifiesto por la variable `KIT_TILE_MANIFEST`. El éxito es la línea `KIT_OK`, no el código de salida.

## Convenciones

- **Rejilla.** Elegir `grid_cm` una sola vez para todo el proyecto (por ejemplo 5.000 cm). El tamaño de la loseta es múltiplo de la rejilla. Ejemplo: 200.000 x 200.000 cm. Unidades siempre en cm.
- **Origen.** Centro de la loseta, Z = 0 en el nivel de referencia. Cuadrada: si no, no gira sin huecos.
- **Bordes.** Cada lado (N, E, S, W) lleva `profile`, `height_cm` y `strip_cm` (franja plana). Dos lados que se tocan deben tener el mismo trío. Camino o cruce justo en el punto medio (`road_center_cm`), así gira y espeja sin romperse. Mejor la misma franja en los 4 lados.
- **Nombres.** Nivel `L_Tile_<ID>` en `/Game/Tiles/`. Actores `<ID>_<Asset>_NN`, carpeta del outliner `/<ID>/Props`.
- **Semilla.** Todo azar (PCG, variación) sale del `tile_id`, nunca de la posición en el mundo.

## Pasos

1. **Manifiesto.** Copiar `tile_manifest.example.json`, rellenar bordes, `placements`, `pcg`.
2. **Validar (sin UE).** `python .claude/skills/build-tile/scripts/validate_tile_manifest.py tile_T01.json`. Debe terminar en `VALID`. Para dos losetas vecinas: `... a.json b.json --adjacent a.json:E:b.json:W`.
3. **Base del nivel.** Lo más simple: `new_tile_level.py` (nivel vacío, sin luces que se dupliquen). Crear el nivel desde la plantilla o duplicar la loseta base. Sin World Partition en la loseta (el Level Instance con WP trae problemas de streaming y bordes). Landscape: el script no lo crea (spawn por Python sin verificar); importar el heightmap a mano una vez y duplicar.
4. **Colocar props.** `run-python.ps1 -Script place_tile.py` con `KIT_TILE_MANIFEST` puesto. Relee el resultado en el outliner (regla de `ue-mcp-safe-edit`).
5. **PCG horneado en el editor.** Un componente PCG **no particionado** por loseta, nodos nativos (Surface Sampler, Spline Sampler, filtros, Static Mesh Spawner con instancias), semilla = ID de loseta. Generar en el editor y dejar la salida guardada en el nivel. El PCG en runtime ignora el transform del Level Instance (Epic, jul-2026): el pasto cambiaría al mover o girar la loseta. Llamar al actor `PCG_<ID>` y correr `bake_pcg.py`: fija `seed` desde el ID (crc32, no `hash()`), exige componente no particionado (`get_editor_property("is_component_partitioned")`: es la UPROPERTY `bIsComponentPartitioned`, no una función), `cleanup_local` + `generate_local(True)` y `clear_pcg_link()` para soltar la salida como actores normales. Falla con `KIT_FAIL` si no aparecen actores (la generación puede ser asíncrona: sin verificar). El pasto va con Landscape Grass, no con PCG.
6. **Luz 100% dinámica.** Nada horneado en la loseta: la luz horneada se rompe al rotar un nivel en streaming, y las luces volumétricas tampoco sirven rotadas.
7. **Prueba de giro.** `rotation_smoke_test.py` para 0/90/180/270: (a) bordes: con `rotatable=true` los 4 bordes deben ser iguales; una loseta N=S y E=W distintos falla porque girada 90 pone bordes distintos juntos; (b) colisión: en un mapa vacío (`KIT_TEST_MAP`) pone 4 Level Instances con yaw 0/90/180/270, juega en PIE (espera `KIT_TILE_PIE_WAIT_S`, 4 s por defecto, a que carguen), traza hacia abajo en 5 puntos por borde (rotados con el mismo yaw) y exige la altura esperada (`KIT_TILE_TOL_CM`, 50 por defecto). Corre por ticks del editor: el script solo la arranca y el resultado sale en el log. Imprime PASS/FAIL por giro; `KIT_OK` solo si pasan los 4. Parte pura: `python rotation_smoke_test.py --pure tile.json`. Falta repetirla en un build empaquetado (colisión de Landscape en niveles girados: evidencia floja). Plan B si falla: cuatro variantes pre-giradas, o no girar el paisaje y girar solo los props.
8. **Presupuesto.** Medir con `stat unit`, `stat gpu`, `stat scenerendering`, `stat memory` y anotar en `stats` del manifiesto. El validador marca ERROR si se pasa.

| Métrica por loseta | Tope propuesto | Por qué |
|---|---|---|
| Triángulos | 400.000 | todas las losetas pueden estar residentes |
| Draw calls | 600 | mallas con instancias (ISM/HISM) en vez de actores sueltos |
| Texturas | 96 MB | 16 losetas son 1,5 GB de 6 GB de VRAM |
| Instancias | 20.000 | costo de PCG y culling |

   Probar `r.Nanite 0/1` con la misma cámara: si el costo fijo supera el ahorro, props sin Nanite. Perfil Bajo con sombras en cascada sin VSM es la referencia de la GPU modesta.
9. **Ojos.** Con `ue-viewport-eyes`: 4 ángulos y la vista `top` para ver cierres y huecos. Criterios: "cierra con la vecina", "sin huecos", "sin material por defecto", "escala correcta". Repetir con la loseta girada 90 y 180.
10. **Cargar en juego.** `Load Level Instance` (Location y Rotation en espacio mundo) desde un nivel persistente. Cargar varias losetas repartidas en cuadros (una cada 0,2 s) para evitar un tirón.

## Trampas

- Mover un prop fuera de la rejilla rompe el encaje en los bordes: respetar `snap_cm`.
- Si se cambia la plantilla de loseta o la versión del motor, repetir la prueba de giro.
- Online: los niveles dinámicos necesitan el mismo nombre en servidor y clientes (sin verificar).

## Estado (verificado el 9-nov-2026, UE 5.8.4)

- De punta a punta en un proyecto C++ en blanco: `new_tile_level.py` (crea la loseta y el mapa de prueba vacíos), `place_tile.py` con `tile_manifest.example.json` (solo formas del motor), y `rotation_smoke_test.py`: 4/4 PASS y `KIT_OK`.
- La prueba de colisión corre en PIE: pone 4 Level Instances girados 0/90/180/270 en el mapa de prueba, juega, traza en el mundo de juego, y al final los borra y guarda. El resultado sale en el log del editor (el script solo la arranca).
- Arreglado: `hit_z` leía el `HitResult` con `get_editor_property` (no se puede en 5.8.4) y toda traza parecía "sin colisión". Ahora usa `to_tuple()`. La nota vieja de que en el mundo del editor no había colisión venía de ese error.
- Sin probar: PCG horneado (`bake_pcg.py`), Landscape dentro de un Level Instance girado, y los topes de presupuesto (son propuestas, no cifras de Epic).

## Verificado en TableFlyer (ronda 8, 9-nov-2026, UE 5.8.4)

- `validate_tile_manifest.py` y `place_tile.py` funcionaron con un juego real. Nuevo: `scale` por pieza (número o [x, y, z]) y `/Engine/BasicShapes/` sin aviso.
- Paso 3: si la loseta sale de `Template_Default`, borrar su luz, cielo, niebla, PlayerStart y piso: si no, se duplican en el nivel persistente.
- `rotation_smoke_test.py`: `set_editor_property('world_asset')` no carga el Level Instance y un `time.sleep` bloquea el hilo del editor. Ahora usa `set_world_asset` + `load_level_instance` y una máquina de estados por ticks (`is_loaded()` sí llega a True).
- (Corregido el 9-nov en la noche: el "sin colisión" del editor era el error de `hit_z`; ver Estado.)
