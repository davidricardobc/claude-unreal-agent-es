"""Coloca los props de un manifiesto de loseta en su nivel (Python de editor de UE 5.8).

Uso con ue-headless/run-python.ps1. Se pasa el manifiesto por variable de entorno:
  KIT_TILE_MANIFEST=C:\\ruta\\tile_T01.json
Imprime una línea PLACED por prop, FAIL por problema y KIT_OK solo si todo salió bien.

Todas las llamadas a la API `unreal.*` están SIN VERIFICAR en 5.8: si una falla,
revisar Intermediate/PythonStub/unreal.py con grep.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate_tile_manifest as vtm  # noqa: E402


def main():
    import unreal  # solo existe dentro de UE

    path = os.environ.get("KIT_TILE_MANIFEST")
    if not path:
        print("FAIL falta KIT_TILE_MANIFEST")
        return False
    with open(path, encoding="utf-8") as f:
        m = json.load(f)

    problems = [t for lvl, t in vtm.validate_manifest(m) if lvl == "ERROR"]
    for t in problems:
        print("FAIL manifiesto: " + t)
    if problems:
        return False

    # Abrir el nivel de la loseta (sin verificar: LevelEditorSubsystem.load_level).
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not les.load_level(m["level"]):
        print("FAIL no se pudo cargar " + m["level"])
        return False

    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    folder = "/%s/Props" % m["tile_id"]
    # Idempotente: borra lo colocado en una corrida anterior antes de volver a colocar.
    old = [a for a in actors.get_all_level_actors() if str(a.get_folder_path()) == folder]
    for a in old:
        actors.destroy_actor(a)
    if old:
        print("LIMPIADOS %d actores previos de %s" % (len(old), folder))
    ok = True
    placed = 0
    for i, p in enumerate(m.get("placements", [])):
        mesh = unreal.EditorAssetLibrary.load_asset(p["asset"])
        if mesh is None:
            print("FAIL placements[%d]: no existe %s" % (i, p["asset"]))
            ok = False
            continue
        x, y, z = p["location_cm"]
        # Los manifiestos tienen el origen en el centro de la loseta, igual que el nivel.
        a = actors.spawn_actor_from_class(
            unreal.StaticMeshActor, unreal.Vector(x, y, z),
            unreal.Rotator(0.0, 0.0, float(p.get("yaw", 0))))
        if a is None:
            print("FAIL placements[%d]: no se pudo crear el actor" % i)
            ok = False
            continue
        a.static_mesh_component.set_static_mesh(mesh)
        # Ronda 8 (TableFlyer): escala opcional por pieza ([x, y, z] o un número). Props importados a otra escala
        # o un piso hecho con /Engine/BasicShapes/Cube no se podían colocar sin ella.
        sc = p.get("scale")
        if sc is not None:
            sc = [float(sc)] * 3 if isinstance(sc, (int, float)) else [float(v) for v in sc]
            a.set_actor_scale3d(unreal.Vector(*sc))
        a.set_actor_label("%s_%s_%02d" % (m["tile_id"], os.path.basename(p["asset"]), i))
        a.set_folder_path(folder)
        placed += 1
        print("PLACED %s" % a.get_actor_label())

    if ok and placed != len(m.get("placements", [])):
        print("FAIL colocados %d de %d" % (placed, len(m.get("placements", []))))
        ok = False
    if ok:
        les.save_current_level()
        print("KIT_OK")
    return ok


if __name__ == "__main__":
    try:
        sys.exit(0 if main() else 1)
    except Exception as e:  # el wrapper decide por KIT_OK, no por el código de salida
        print("FAIL excepcion: %r" % (e,))
        sys.exit(1)
