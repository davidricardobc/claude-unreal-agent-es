---
name: ue-mcp-safe-edit
description: Capa de reglas que acompaña a cualquier escritura por MCP (también cuando la hacen gdd-to-datatables o asset-intake). Reglas cortas para escribir de forma segura en un proyecto de Unreal Engine 5.8 por el MCP de Epic: leer, escribir, releer y comparar; un escritor por editor; guardar solo el paquete tocado; no borrar assets referenciados; qué hacer tras un tiempo agotado; lógica en C++ y Blueprints delgados; orden obligado de USTRUCT y clases base antes de abrir el editor; límites de Live Coding. Úsala cada vez que vayas a crear o cambiar assets, actores, Blueprints, Data Tables o niveles por MCP. Frases disparadoras - "edita el nivel", "crea el Blueprint", "cambia esta propiedad", "importa estas tablas", "borra estos assets", "se agotó el tiempo", "safe edit", "write through MCP", "modify the level", "timeout from the tool".
---

# ue-mcp-safe-edit

Las escrituras por MCP pueden "tener éxito" sin hacer lo pedido, o terminar después de un tiempo agotado. Estas reglas cubren eso. No importa ni crea nada por sí sola: es la capa que acompaña a las skills que escriben. Si no se hizo el preflight en esta sesión, correr antes `ue-session-preflight`.

**Cómo se llama (verificado en 5.8.4).** Tres metaherramientas: `list_toolsets`, `describe_toolset` (`toolset_name`) y `call_tool` (`toolset_name` largo + `tool_name` corto + `arguments`). Nombres largos: `editor_toolset.toolsets.scene.SceneTools`, `...asset.AssetTools`, `...object.ObjectTools`, `...data_table.DataTableTools`, `...programmatic.ProgrammaticToolset`; los de C++ van como `EditorToolset.EditorAppToolset`. Mandar siempre la cabecera `Mcp-Session-Id` que da `initialize`. Los parámetros sin valor por defecto son obligatorios aunque el schema no lo diga (ejemplo: `find_actors` pide `name`, `tag` y `collision_channels`).

## Las 12 reglas

1. **Leer, escribir, releer, comparar.** Antes: leer el valor actual. Después: releer y comparar con lo pedido. Una escritura que responde ok puede haber ignorado una clave mal escrita. Sin relectura, no se da por hecho.
2. **Un escritor por editor.** Lecturas en paralelo sí; escrituras en serie, una llamada a la vez, sin solapar. Dos agentes escribiendo en el mismo editor no es válido. Si hay varios editores en una máquina, un puerto fijo por proyecto.
3. **Nombres exactos.** Propiedades UPROPERTY en PascalCase (snake_case a veces no hace nada y no avisa). La ruta de clase de un Blueprint lleva `_C` (`/Game/Blueprints/BP_Avion.BP_Avion_C`). Antes de llamar una herramienta, `describe_toolset`; no adivinar firmas.
4. **Guardar solo el paquete tocado.** Nunca "Save All". Guardar antes de leer del disco, y antes de entrar en PIE si hay Niagara o MetaSound (un fallo borra lo no guardado).
5. **Respaldo y bloqueo antes de la primera escritura.** Commit o rama de respaldo, y `git lfs lock` del `.uasset` que se va a tocar. Nadie edita carpetas de otro dueño. Commit después de cada bloque que funcionó.
6. **Lotes chicos.** Máximo unas 10 operaciones por ronda; verificar la ronda; commit; seguir. Una edición masiva sin verificación intermedia no se puede reparar.
7. **No borrar assets referenciados.** Antes de borrar o mover: `AssetTools.get_referencers` (y `get_dependencies` para lo contrario). Si devuelve algo, no se borra sin preguntar. No crear y borrar actores a toda prisa: provoca cuelgues.
8. **Tras un tiempo agotado: no repetir.** Las herramientas tienen un límite (cerca de 60 s) y la operación pudo terminar. Pasos: esperar unos segundos, releer el estado, decidir. Si el editor no responde, dejar de llamar y pedir a la persona que mire si hay un diálogo abierto, una compilación o un cuelgue. Repetir una escritura a ciegas duplica actores y assets.
9. **Lógica en C++, Blueprints delgados.** El Blueprint solo guarda parámetros, referencias a assets y eventos que llaman a C++. No generar grafos grandes por MCP: salen como espagueti, no se leen y ocultan roturas de cambios en C++.
10. **Orden obligado.** Primero en C++ todas las `USTRUCT` de filas de tablas (`FTableRowBase`) y las clases base. Compilar con el editor cerrado (`ue-headless`). Recién entonces abrir el editor y hacer Blueprints, datos y niveles por MCP.
11. **Live Coding solo cambia cuerpos de funciones.** No agrega ni quita `UFUNCTION`, `UPROPERTY` ni `USTRUCT` de forma segura: eso pide cerrar y recompilar. Cambiar un valor por defecto en el constructor no actualiza instancias ya creadas. No desactivar el reinstancing (suele colgar el editor).
12. **`execute_tool_script` no es Python libre.** Es un sandbox para encadenar herramientas en una sola llamada: solo importa `json`, `math`, `re`, `time`, `datetime` y `copy`, `open` es de solo lectura, no hay `import unreal`, y el script define `run()` que devuelve un dict y llama `execute_tool(nombre_largo, json_str)` (`programmatic.py`). Llamar `get_execution_environment` una vez antes. No abre transacción (la clase transaccional existe pero no se usa): el deshacer es git. Sirve para lotes (un nivel entero en 3 llamadas), con las mismas reglas 1 a 8. Nunca `--dangerously-skip-permissions` con el plugin cargado. Nunca exponer el puerto.

## Ciclo estándar por cambio

1. `describe_toolset` del toolset (una vez por sesión) y lectura del estado actual.
2. Escritura con `call_tool`, un cambio.
3. Relectura del mismo valor. Comparar con lo pedido. Si no coincide: no reintentar igual; revisar PascalCase, `_C`, ruta del asset.
4. Guardar solo ese paquete. Releer del disco si importa.
5. Anotar en una línea (qué, dónde, verificado sí o no). Esa línea alimenta la bitácora.

## Casos frecuentes

- **Data Tables:** el CSV o JSON del repo es la fuente de verdad. Para una fila suelta: `DataTableTools.add_rows`, `set_rows` (valores como string JSON), `get_rows`, `list_rows`, `remove_rows`, `rename_rows`. Para la tabla entera: importar el CSV (vacía antes de llenar) a una temporal, validar y reemplazar. Structs C++, no de Blueprint.
- **Nivel nuevo:** no hay herramienta de "nuevo nivel". `AssetTools.duplicate` de `/Engine/Maps/Templates/Template_Default` a `/Game/Maps/X`. `load_level` falla si el Untitled tiene cambios ("Save the level before loading it").
- **Actores:** `SceneTools.add_to_scene_from_class` con `actor_type.refPath="/Script/Modulo.Clase"` (o la ruta `_C` de un Blueprint); `name` es la etiqueta, el nombre real queda `Clase_N`. `ObjectTools.set_properties(instance, values)` toma `values` como string JSON y vuelve a correr OnConstruction; `get_properties(instance, properties)` lee una lista de nombres; `ActorTools.set_actor_transform(actor, xform, worldspace=true)`. Nombres de parámetro tal cual (`instance`, `properties`, `xform`, `worldspace`), verificados en `object.py` y `actor.py`.
- **Probar input en PIE:** `SlateInspector.PressKey` no llega al juego. Usar una UPROPERTY de depuración en el pawn y cambiarla con `set_properties` sobre `/Game/Maps/UEDPIE_0_<Mapa>.<Mapa>:PersistentLevel.<Pawn>_0`; leer con `ActorTools.get_actor_transform`.
- **Pruebas por MCP:** `AutomationTestToolset.DiscoverTests` primero (si no, resultados vacíos).
- **`TSoftObjectPtr` a mallas:** vacías al crear; llenarlas en una segunda pasada.
- **Un `.uasset` que alguien más editó:** no hay fusión. Pedir el bloqueo, hacer pull, y rehacer el cambio sobre su versión.

## Trampas

- Guardar antes de PIE si hay Niagara o MetaSound.
- "Save All" guarda cosas que nadie revisó y llena el commit de ruido: guardar solo lo tocado.
- Tras recompilar con el editor cerrado, la sesión MCP se cae; correr de nuevo `ue-session-preflight`.

## Pruebas de la skill

`python -I .claude/skills/ue-mcp-safe-edit/tests/test_skill.py` (comprueba que el SKILL.md sigue completo: 12 reglas, ciclo, que cada punto "sin verificar" trae cómo verificarlo y que no vuelva la idea de Python libre en `execute_tool_script`). Esta skill no tiene scripts: las reglas se prueban en vivo con el editor.

## Sin verificar (confirmar el día 1, cada uno en 1 a 2 minutos)

- El límite real de tiempo por llamada en 5.8.4 (60 s sale de un blog). Verificar: `execute_tool_script` con `import time` y `def run(): time.sleep(70); return {}`, y ver si corta.
- Si las herramientas sueltas (por ejemplo `set_properties`) abren transacción. Verificar: cambiar una propiedad por MCP y pulsar Ctrl+Z en el editor. Si no deshace, git es el único deshacer.
- Si en 5.8.4 sigue la prohibición de llamadas solapadas. Verificar: dos lecturas a la vez y mirar si una falla. La regla 2 es la segura mientras tanto.
- El formato exacto de `values` en `DataTableTools.set_rows`. Verificar: `get_rows` de una fila y devolver lo mismo con un campo cambiado.
