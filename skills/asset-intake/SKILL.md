---
name: asset-intake
description: Mete assets de terceros o de IA a un proyecto de Unreal Engine 5.8 de forma ordenada. Importa FBX/GLB por lotes con escala en cm, pivote, colisión simple o convexa, LODs y Nanite opcional; nombra con prefijos SM_, M_, MI_, T_ y ordena carpetas; migra packs comprados (por ejemplo Synty) a la carpeta del proyecto; lleva un registro de licencias en CSV con validador y genera la lista de assets de terceros para la entrega. Reglas duras - Synty no sale del equipo ni se sube a generadores 3D de IA; los assets de IA se declaran y se revisan. Frases disparadoras - "importa este FBX", "importa estos modelos", "migra el pack de Synty", "registra la licencia", "lista de assets de terceros", "import assets in batch", "asset license registry", "intake a Meshy model".
---

# asset-intake

Cada asset que entra queda con escala correcta, colisión, nombre por convención y una fila de licencia. Sin esa fila no entra al repo. Genérica: ejemplos ficticios, cifras a medir.

## Antes de empezar

1. `ue-session-preflight` en la sesión. Escrituras por MCP: seguir `ue-mcp-safe-edit`.
2. Scripts en `.claude/skills/asset-intake/scripts/`: `asset_rules.py` y `license_registry.py` (puros), `batch_import.py` y `migrate_pack.py` (editor), `api_probe.py` + `api.txt` (sonda: día 1, corre con `run-python.ps1` y dice qué `unreal.*` faltan y si cada una es función o propiedad; usa la sonda compartida de `ue-headless`), ejemplos `import_batch.example.json` y `licenses.example.csv`.
3. Los de editor se corren con `ue-headless` (`run-python.ps1`), parámetros por variable de entorno. El éxito es la línea `KIT_OK`. Siempre desde PowerShell: Git Bash convierte `/Game/...` en `C:/Program Files/Git/Game/...`. Para un archivo suelto (audio, textura) basta el commandlet `UnrealEditor-Cmd.exe <proj> -run=ImportAssets -source=<archivo> -dest=/Game/<Carpeta> -nosourcecontrol -replaceexisting -unattended` (verificado, ~20 s).

## Reglas de licencia (primero, antes de importar)

- **Synty.** Los archivos no salen del equipo: no van a git público, ni a itch, ni a la nube compartida. Tampoco se usan como imagen de referencia ni se suben a Meshy, Tripo o cualquier generador 3D de IA. Los packs van en `.gitignore`; comprobarlo con `python scripts/license_registry.py gitignore <repo> Content/ThirdParty/Synty/x.fbx` (ERROR si git no lo ignora). Cada pack: leer su ficha y su licencia (única o suscripción).
- **IA 3D (Meshy, Tripo, similares).** Se declaran siempre. Se revisa topología, UV y escala antes de usarlos (`reviewed=yes`). Meshy plan gratis: CC BY 4.0 con crédito ("Model created with Meshy - CC BY 4.0 License"); plan pago: confirmar el costo con la persona antes de gastar. La imagen de entrada debe ser propia, nunca de Synty ni de terceros. Tripo: sus páginas se contradicen; no usarlo sin leer sus términos al día.
- **CC0 (Kenney, Poly Haven).** Sin crédito, pero igual va al registro.
- **Hunyuan3D-2.** Su licencia excluye UE, Reino Unido y Corea del Sur: el validador lo marca ERROR.
- Licencia desconocida: no entra.
- Las reglas de una competencia concreta (qué declarar) salen de sus reglas oficiales, no de aquí.

## Registro de licencias

CSV con columnas `asset, source, license, allowed_use, declare` (yes/no) y opcionales `ai_generated, reviewed, uploaded_to_ai, credit_text, url, notes`. Plantilla: `licenses.example.csv`.

```
python .claude/skills/asset-intake/scripts/license_registry.py validate assets-licenses.csv
```

Termina en `VALID` o `INVALID`. Marca ERROR si: asset de IA sin declarar o sin revisar, CC BY sin `credit_text` (la licencia exige atribución, sea IA o no), Synty subido a IA, Hunyuan, licencia desconocida, duplicados.

## Importar por lotes

1. Dejar los archivos en una carpeta de entrada fuera del repo. Una fila en el registro por cada uno.
2. Escribir el lote (`import_batch.example.json`): `source`, `base` (nombre libre), `origin` (`own`, `third_party`, `ai`), `pack`, `category`, `target_max_cm`, `collision` (`box`, `convex`, `none`), `nanite`, `lods`.
3. Correr con `KIT_IMPORT_BATCH=lote.json` y, si se quiere, `KIT_IMPORT_REPORT`. Una sola importación a la carpeta final con el nombre `SM_...`; se toma el primer StaticMesh (no un material), se renombran materiales y texturas (`M_`, `MI_`, `T_`), se mide, se escala con `build_scale3d` del LOD 0 y se vuelve a medir. Al final guarda cada paquete creado: primero materiales y texturas (con su nombre nuevo), luego la malla. `rename_asset` no guarda, y en commandlet lo no guardado se pierde al cerrar.
4. Leer el informe CSV (`Saved/asset-intake-report.csv`): `OK`, `WARN` (pivote) o `FAIL` (medida final fuera del objetivo, sin colisión, un paquete que no se pudo guardar, excepción). Cada fila dice "guardados N de M paquetes": si N < M es FAIL. `KIT_OK` solo si no hay FAIL y hay una fila por item. El informe va a `Saved/` del proyecto.

Convenciones:

| Tipo | Prefijo | Ejemplo |
|---|---|---|
| Static Mesh | `SM_` | `SM_WoodCrate_01` |
| Material | `M_` | `M_Wood` |
| Material Instance | `MI_` | `MI_WoodDark` |
| Textura | `T_` + sufijo `_D`, `_N`, `_ORM`, `_E` | `T_Wood_D` |

- Carpetas: `/Game/Art` (propio), `/Game/ThirdParty/<Fuente>/<Pack>/<Categoria>`, `/Game/AI_Generated/<Servicio>/<Categoria>`. PascalCase, sin espacios ni tildes.
- **Escala.** UE trabaja en cm. Un GLB suele venir en metros. Se mide la caja y se escala a la medida objetivo (`target_max_cm`); sin objetivo, `guess_scale` da una pista (menor de 5 = metros) que hay que confirmar.
- **Pivote.** Al piso y centrado salvo que el objeto lo pida. El script lo informa; si está mal, corregirlo en el DCC o con Modeling Tools.
- **Colisión.** Sin colisión una malla no sirve para choques. Caja para edificios y cajas, convexa para rocas y formas orgánicas, ninguna para decoración lejana. Nunca colisión compleja como colisión de juego salvo que se pruebe el costo.
- **LODs y Nanite.** Los meshes de pocos triángulos casi no necesitan Nanite. Prueba de 10 minutos por escena: `r.Nanite 0/1` con la misma cámara y `stat gpu`. `lods: N` genera N LODs por `StaticMeshEditorSubsystem.set_lods`; `nanite: true` activa `nanite_settings`.
- **Material.** Instancia de un material maestro propio; revisar que no quede el cuadriculado gris por defecto.

## Migrar un pack comprado

Ruta por pack, en este orden: (1) ficha con versiones de UE; si hay 5.3, usar esa. (2) Solo UE4: abrir en 4.27, Migrate, abrir la copia en 5.8 y resguardar todo. (3) Si falla: FBX más una textura de paleta y un material maestro propio. Migrate vuelve a guardar en el formato de origen: probar siempre la copia.
Luego (mueve la carpeta con `rename_directory`; `KIT_PACK_COPY=1` duplica y dobla el espacio) `KIT_PACK_SRC=/Game/_Migrated/<Pack> KIT_PACK_DST=/Game/ThirdParty/Synty/<Pack>` con `migrate_pack.py`: avisa por malla sin colisión simple o con material por defecto, y recuerda arreglar redirectores. Anotar licencia y origen en el registro.

## Lista de assets de terceros (entrega)

```
python .claude/skills/asset-intake/scripts/license_registry.py checklist assets-licenses.csv -o third-party-assets.md
```

Solo filas con `declare=yes`, agrupadas por fuente, con licencia, enlace, crédito y marca de IA. Cuenta al final los no declarados para revisarlos una vez más. No genera si el CSV tiene ERROR.

## Pruebas de la skill

`python -I .claude/skills/asset-intake/tests/test_asset_intake.py` (23 pruebas, sin Unreal). Incluye el guardado de secundarios con un `unreal` falso y el enum de colisión vigente.

## Sin verificar (confirmar el día 1)

- `AssetImportTask` y el importador de GLB (Interchange) en 5.8. Si `Interchange.FeatureFlags.Import.FBX` está activo, `FbxImportUI` puede ignorarse. Prueba de 1 minuto: importar un cubo de 1 m y leer `get_bounds()`.
- `StaticMeshEditorSubsystem` (set_convex_decomposition_collisions, set_lods, get/set_nanite_settings, get/set_lod_build_settings); `EditorStaticMeshLibrary` está deprecada y no se usa. Confirmado en headers de 5.8: `add_simple_collisions` recibe `unreal.ScriptCollisionShapeType` (el viejo `ScriptingCollisionShapeType` ya no existe), `save_asset(ruta, only_if_is_dirty)` y que `rename_asset` no guarda.
- `StaticMesh.get_bounds`, `static_materials`, `EditorAssetLibrary.duplicate_directory` y `delete_directory`.
- Términos actuales de Meshy y Tripo; que el plan gratis de Meshy permita descargas.
