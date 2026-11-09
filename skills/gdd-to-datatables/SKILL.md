---
name: gdd-to-datatables
description: Convierte las tablas de un documento de diseño (markdown o CSV) en datos de Unreal Engine 5.8. Genera CSV en UTF-8 con BOM, el header C++ de la USTRUCT (FTableRowBase), valida filas (tipos, rangos, IDs únicos, referencias cruzadas), importa a Data Tables con Python de editor haciendo respaldo antes y sugiere Gameplay Tags. Genérica, sirve para cualquier proyecto. Úsala al pasar números de diseño a datos. Frases disparadoras - "pasa las tablas del GDD a Data Tables", "genera el struct de la tabla", "importa este CSV a Unreal", "valida las tablas", "sugiere gameplay tags", "GDD to data tables", "import CSV to DataTable".
---

# gdd-to-datatables

Pipeline: tabla del GDD (md o CSV) -> CSV limpio + esquema -> validar -> USTRUCT en C++ -> compilar -> importar. El GDD manda; los CSV viven en el repo (`Content/Data/Source/`) y se pueden regenerar.

Scripts en `.claude/skills/gdd-to-datatables/scripts/` (solo biblioteca estándar de Python 3). Todos imprimen `KIT_OK` al terminar bien, `KIT_FAIL` si no. Probados solo con datos ficticios (`tests/test_gdd.py`), nunca contra Unreal.

## Marcadores

- `<Fuente>`: `.md` con tablas o `.csv`. `<Out>`: `Content/Data/Source`. `<Modulo>`: módulo C++ del juego.

## Pasos

1. **Parsear y normalizar.** `python .claude/skills/gdd-to-datatables/scripts/gdd_tables.py <Fuente> --out <Out> [--tag-prefix Weapon]`. Cada tabla markdown (el título es el último `#` previo) produce `DT_<Titulo>.csv` y `DT_<Titulo>.schema.json`. Con `--list` solo muestra lo hallado.
   - Primera columna = `RowName`, convertida a clave ASCII estable (`Rifle Ligero` -> `Rifle_Ligero`). El texto original queda en la columna `DisplayName` (tipo `text`), no en la clave.
   - Encabezados a identificadores válidos (`Daño (dps)` -> `Dano_dps`). Coma decimal a punto (avisa con `KIT_WARN` si parece separador de miles, ej. `1,000`). Encabezados que normalizan igual (`Daño` y `Dano`) dan `KIT_FAIL`.
   - CSV en UTF-8 con BOM, LF.
2. **Revisar el esquema.** Los tipos son inferidos (`int`, `float`, `bool`, `string`). Editar el `.schema.json` a mano o con ayuda: agregar `min`, `max`, `allowed`, `required`, `ref` (`"DT_Armas.RowName"`), o cambiar un tipo a `tag`, `text` o `name`. Confirmar con la persona los rangos que no estén en el GDD; no inventarlos.
3. **Validar.** `python .claude/skills/gdd-to-datatables/scripts/validate_rows.py <csv> <schema> --refs <otros.csv>`. Revisa columnas, tipos, rangos, RowName único, valores permitidos y referencias cruzadas. Corregir en el GDD o en el CSV fuente, no en el asset.
4. **Generar la USTRUCT.** `python .claude/skills/gdd-to-datatables/scripts/gen_ustruct.py <schema> --out Source/<Modulo>/Data --api <MODULO>_API`. Crea `<Nombre>Row.h` con `USTRUCT(BlueprintType) struct F...Row : public FTableRowBase`. Con columnas `tag`, agregar `GameplayTags` a `PublicDependencyModuleNames` en el `.Build.cs`.
5. **Compilar con el editor cerrado.** Una USTRUCT nueva o cambiada no entra por Live Coding. Usar la skill `ue-headless` (`build.ps1`) y pedir "cerrar y reabrir el editor" si estaba abierto.
6. **Importar.** Con `ue-headless/scripts/run-python.ps1` y `.claude/skills/gdd-to-datatables/scripts/import_datatable.py`. Parámetros por variables de entorno: `KIT_DT_ASSET`, `KIT_DT_CSV`, `KIT_DT_STRUCT` (`/Script/<Modulo>.<Nombre>Row`, sin la F), `KIT_DT_BACKUP`.
   - `fill_data_table_from_csv_file(tabla, csv, struct)` **vacía la tabla antes de llenarla** y sobrescribe sin aviso. El script respalda a CSV en `Saved/DataTableBackups/` primero.
   - Si no puede respaldar (`export_data_table_to_csv_file`), falla con `KIT_FAIL` y no toca la tabla. Verifica que la tabla use el mismo struct. `KIT_OK` solo si las filas importadas coinciden con las del CSV; si no, no guarda el asset.
   - Primera importación: dejar vacías las columnas de referencias a mallas o assets (`TSoftObjectPtr`) y llenarlas en una segunda pasada con rutas completas.
7. **Etiquetas.** Con `--tag-prefix` se escribe `<tabla>.tags.txt` (una etiqueta por fila, `Weapon.Rifle_Ligero`) y `.tags.ini` (líneas `+GameplayTagList=(Tag="...",DevComment="")`). Pegar al `Config/DefaultGameplayTags.ini` o importar como Data Table de `GameplayTagTableRow` registrada en Project Settings > Gameplay Tag Table List. Proponerlas a la persona antes de escribirlas; evitar cadenas sueltas en el código.
8. **Verificar.** Abrir el Data Table, o con el editor abierto `DataTableTools.list_rows` por MCP (toolset `editor_toolset.toolsets.data_table.DataTableTools`); una fila suelta se corrige con `add_rows`/`set_rows`, siempre desde el CSV fuente y comparar el conteo de filas con el CSV. Reportar `KIT_OK` solo si coincide.

## Reglas

- No editar el asset a mano si el CSV es la fuente: la siguiente importación lo borra.
- Un CSV por tabla, un struct por tabla. Curvas reales (XP por nivel) van en CurveTable; lo demás en Data Table con columnas explícitas.
- Si la validación falla, no importar. Mostrar los problemas con línea y columna.
- Sin contenido de un juego concreto en esta skill: los ejemplos son ficticios.

## Sin verificar (confirmar el día 1 con Unreal)

- `export_data_table_to_csv_file`, `get_data_table_row_names` y `fill_data_table_from_csv_file` figuran en la referencia de Epic; `get_data_table_row_struct` confirmado en `DataTableFunctionLibrary.h` de 5.8. Lista completa en `api.txt`: verificar con la sonda compartida (`run-python.ps1 -Script .claude/skills/ue-headless/scripts/api_probe.py` con `KIT_API_SKILLS=gdd-to-datatables`, 1 minuto).
- Que `DataTableFactory` con `factory.struct` cree la tabla en 5.8 (la propiedad figura en la doc; la creación se probó en 5.6).
- Que el nombre de la primera columna del CSV sea irrelevante (se escribe `Name`).
- Formato de línea de `DefaultGameplayTags.ini` y el módulo `GameplayTags` en `.Build.cs`.
- Metadatos `ClampMin/ClampMax` en UPROPERTY no se aplican al importar CSV, solo al editar.

## Pruebas de la skill

`python -I .claude/skills/gdd-to-datatables/tests/test_gdd.py` (sin Unreal; termina en `KIT_OK test_gdd`).

## Verificado en TableFlyer (ronda 8, 9-nov-2026, UE 5.8.4)

- Pipeline completo en un juego real: mini GDD con 2 tablas -> CSV -> esquema -> `validate_rows.py` -> `gen_ustruct.py` -> compilar -> `import_datatable.py` -> `KIT_OK` (8 y 7 filas). El juego lee las tablas con `FindRow`/`GetRowMap`.
- Arreglado: `yes/no` y `si/no` del GDD ahora se infieren como bool y se escriben `true/false` (UE solo acepta esos). Nuevo `--struct-prefix TF` (FTFPlanesRow) para no chocar con structs de otros módulos.
- `import_datatable.py` también corre en un editor abierto: poner las variables `KIT_DT_*` en `os.environ` y `runpy.run_path` con `upy.py` (sin cerrar el editor).
- `gen_ustruct.py` ahora escribe su comentario en inglés (un juego para público internacional va en inglés).
