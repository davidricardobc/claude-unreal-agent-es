"""Script de editor: importa un CSV a un Data Table (lo crea si no existe). Corre con ue-headless/run-python.ps1.

Parámetros por variables de entorno (el wrapper no pasa argumentos):
  KIT_DT_ASSET   ruta del asset, ej. /Game/Data/DT_Items
  KIT_DT_CSV     ruta absoluta del CSV
  KIT_DT_STRUCT  ruta del struct, ej. /Script/MiModulo.ItemsRow  (sin la F)
  KIT_DT_BACKUP  carpeta de respaldos (por defecto <proyecto>/Saved/DataTableBackups)
ATENCIÓN: fill_data_table_from_csv_file VACIA la tabla antes de llenarla. Se respalda a CSV primero.
KIT_OK solo si las filas importadas coinciden con el CSV; si no puede respaldar, falla sin tocar la tabla.
Verificado en UE 5.8.4 (TableFlyer, ronda 8): la creación de la tabla y la importación (KIT_OK con 2 tablas).
Sin probar: la rama de tabla existente (respaldo y get_data_table_row_struct; correr api_probe o revisar PythonStub).
"""
import csv
import os
import time

import unreal

asset = os.environ["KIT_DT_ASSET"]
csv_path = os.environ["KIT_DT_CSV"]
struct_path = os.environ["KIT_DT_STRUCT"]
backup_dir = os.environ.get("KIT_DT_BACKUP") or os.path.join(unreal.Paths.project_saved_dir(), "DataTableBackups")

struct = unreal.load_object(None, struct_path)
if struct is None:
    print("KIT_FAIL struct no encontrado (compilar con el editor cerrado primero): " + struct_path)
    raise SystemExit(1)

lib = unreal.DataTableFunctionLibrary


def fail(msg):
    print("KIT_FAIL " + msg)
    raise SystemExit(1)


def count_csv_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return sum(1 for r in csv.reader(f) if any(c.strip() for c in r)) - 1  # sin encabezado


expected = count_csv_rows(csv_path)

if unreal.EditorAssetLibrary.does_asset_exist(asset):
    table = unreal.EditorAssetLibrary.load_asset(asset)
    # La importación vacía la tabla: sin respaldo no se sigue. export_data_table_to_csv_file existe en 5.x (doc de Epic).
    os.makedirs(backup_dir, exist_ok=True)
    bak = os.path.join(backup_dir, "%s_%s.csv" % (asset.rsplit("/", 1)[1], time.strftime("%Y%m%d_%H%M%S")))
    if not lib.export_data_table_to_csv_file(table, bak) or not os.path.isfile(bak):
        fail("no se pudo respaldar la tabla en %s; no se importa" % bak)
    print("KIT_INFO respaldo", bak)
    if lib.get_data_table_row_struct(table) != struct:  # rama sin ejecutar todavía; nombre confirmado en el header de 5.8
        fail("la tabla usa otro struct que %s; no se importa" % struct_path)
else:
    folder, name = asset.rsplit("/", 1)
    factory = unreal.DataTableFactory()
    factory.struct = struct
    table = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.DataTable, factory)
    if table is None:
        fail("no se pudo crear la tabla " + asset)
    print("KIT_INFO tabla creada", asset)

if not lib.fill_data_table_from_csv_file(table, csv_path, struct):
    fail("fill_data_table_from_csv_file devolvio False")
got = len(lib.get_data_table_row_names(table))
print("KIT_INFO filas importadas: %d (CSV: %d)" % (got, expected))
if got != expected:
    fail("el conteo de filas no coincide; NO se guarda el asset (respaldo en %s)" % backup_dir)
unreal.EditorAssetLibrary.save_asset(asset)
print("KIT_OK")
