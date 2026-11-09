"""Lleva un pack comprado (ya migrado a /Game/_Migrated) a la carpeta del proyecto y lo revisa.

Entorno: KIT_PACK_SRC (ej. /Game/_Migrated/PolygonFarm), KIT_PACK_DST (ej. /Game/ThirdParty/Synty/PolygonFarm),
KIT_PACK_COPY=1 para duplicar en vez de mover (doble espacio en disco; un pack puede pesar GB).
Por defecto MUEVE con rename_directory (no deja _Migrated duplicado) y avisa de redirectores.
Lista mallas sin colisión simple o con material por defecto. Los packs de Synty se quedan en
esta máquina: no se suben a ningún servicio. Llamadas `unreal.*` SIN VERIFICAR en 5.8 (api.txt).
KIT_OK solo si se movió/copió y la revisión terminó; KIT_FAIL en otro caso.
"""
import os
import sys


def run():
    import unreal

    src, dst = os.environ["KIT_PACK_SRC"], os.environ["KIT_PACK_DST"]
    lib = unreal.EditorAssetLibrary
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if not lib.does_directory_exist(src):
        print("KIT_FAIL no existe " + src)
        return False
    copy = os.environ.get("KIT_PACK_COPY") == "1"
    moved = lib.duplicate_directory(src, dst) if copy else lib.rename_directory(src, dst)
    if not moved:
        print("KIT_FAIL no se pudo %s a %s" % ("duplicar" if copy else "mover", dst))
        return False
    meshes = no_collision = default_mat = 0
    for path in lib.list_assets(dst, recursive=True, include_folder=False):
        a = lib.load_asset(path)
        if isinstance(a, unreal.StaticMesh):
            meshes += 1
            if sub.get_simple_collision_count(a) == 0:
                no_collision += 1
                print("WARN sin colision: " + path)
            mats = [s.material_interface for s in a.static_materials]
            if any(m is None or "WorldGridMaterial" in m.get_path_name() for m in mats):
                default_mat += 1
                print("WARN material por defecto: " + path)
    print("RESUMEN mallas=%d sin_colision=%d material_por_defecto=%d" % (meshes, no_collision, default_mat))
    if not copy:
        print("PENDIENTE arreglar redirectores en %s (Content Browser > Fix Up Redirectors)" % src)
    lib.save_directory(dst)
    return meshes > 0


if __name__ == "__main__":
    try:
        ok = run()
    except Exception as e:
        print("KIT_FAIL excepcion: %r" % (e,))
        ok = False
    print("KIT_OK" if ok else "KIT_FAIL sin mallas o con error")
    sys.exit(0 if ok else 1)
