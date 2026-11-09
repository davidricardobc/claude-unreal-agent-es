"""Python de editor: crea el nivel vacío de la loseta (el "level" del manifiesto) y el mapa de prueba vacío (KIT_TEST_MAP) si faltan.
Un nivel vacío no tiene luces, cielo ni piso, así que nada se duplica cuando la loseta se instancia en un nivel persistente.
Entorno: KIT_TILE_MANIFEST (JSON), KIT_TEST_MAP (opcional, ej. /Game/Maps/L_TileTest). Imprime KIT_OK.
Verificado en un proyecto C++ en blanco de UE 5.8.4 (9-nov-2026). Correr cada script de editor en su propia llamada: cargan niveles."""
import json, os, unreal

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eal = unreal.EditorAssetLibrary
m = json.load(open(os.environ["KIT_TILE_MANIFEST"], encoding="utf-8"))
made = []
for path in [m["level"], os.environ.get("KIT_TEST_MAP")]:
    if path and not eal.does_asset_exist(path):
        if not les.new_level(path):
            print("KIT_FAIL no se pudo crear " + path)
            raise SystemExit(1)
        les.save_current_level()
        made.append(path)
print("KIT_INFO creados: %s" % (", ".join(made) or "ninguno (ya existian)"))
print("KIT_OK")
