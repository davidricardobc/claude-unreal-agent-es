"""Importación por lotes de FBX/GLB con escala, colisión, LODs, Nanite y informe (UE 5.8, editor).

Entorno: KIT_IMPORT_BATCH (JSON, ver import_batch.example.json); KIT_IMPORT_REPORT (CSV de
salida, default <Saved>/asset-intake-report.csv). Flujo por item, con UNA sola importación:
  1. importa a la carpeta final con el nombre final (SM_...), a escala 1;
  2. toma el primer StaticMesh importado y renombra materiales y texturas (M_, MI_, T_);
  3. mide la caja, calcula la escala y la aplica como build_scale3d del LOD 0;
  4. colisión (box | convex | none), LODs, Nanite; guarda cada paquete creado (materiales,
     texturas y al final la malla) y anota en el informe cuántos se guardaron;
  5. verifica la medida final: fuera del objetivo = FAIL.
KIT_OK solo si todos los items quedaron OK/WARN y el informe se escribió con una fila por item.

Usa StaticMeshEditorSubsystem (EditorStaticMeshLibrary está deprecada). Verificado en headers
de 5.8: AddSimpleCollisions recibe EScriptCollisionShapeType (unreal.ScriptCollisionShapeType) y
RenameAsset no guarda. El resto: confirmar con api_probe.py (ver api.txt). El importador de GLB es
Interchange; la escala se corrige midiendo después, así que no depende de su opción de escala.
Nunca importar ni subir packs de Synty a generadores 3D de IA.
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import asset_rules as rules  # noqa: E402


def import_one(unreal, source, dest_folder, dest_name):
    """Importa a escala 1 y devuelve la lista de rutas importadas."""
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", source)
    task.set_editor_property("destination_path", dest_folder)
    task.set_editor_property("destination_name", dest_name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    if source.lower().endswith(".fbx"):
        ui = unreal.FbxImportUI()
        ui.set_editor_property("import_as_skeletal", False)
        ui.set_editor_property("import_materials", True)
        ui.set_editor_property("import_textures", True)
        task.set_editor_property("options", ui)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    return list(task.get_editor_property("imported_object_paths"))


def pick_static_mesh(unreal, paths):
    for p in paths:
        a = unreal.EditorAssetLibrary.load_asset(p)
        if isinstance(a, unreal.StaticMesh):
            return p, a
    return None, None


def rename_secondaries(unreal, paths, mesh_path, folder):
    """Renombra materiales, instancias y texturas con su prefijo.
    Devuelve (avisos, rutas_de_paquete_finales) de cada secundario, renombrado o no.
    rename_asset NO guarda (termina en AssetTools.RenameAssets): hay que guardar cada ruta."""
    notes, finals = [], []
    for p in paths:
        if p == mesh_path:
            continue
        a = unreal.EditorAssetLibrary.load_asset(p)
        kind = None
        if isinstance(a, unreal.MaterialInstanceConstant):
            kind = "material_instance"
        elif isinstance(a, unreal.Material):
            kind = "material"
        elif isinstance(a, unreal.Texture):
            kind = "texture"
        if kind is None:
            continue
        old = p.split(".")[0]
        new = "%s/%s" % (folder, rules.secondary_name(kind, old.rsplit("/", 1)[-1]))
        if new != old and not unreal.EditorAssetLibrary.rename_asset(old, new):
            notes.append("no se pudo renombrar " + old)
            finals.append(old)
        else:
            finals.append(new)
    return notes, finals


def save_packages(unreal, package_paths):
    """Guarda cada paquete (secundarios primero, la malla al final). Devuelve (guardados, avisos).
    Con run-python.ps1 (commandlet) lo que no se guarda se pierde al cerrar."""
    saved, notes = 0, []
    for pkg in package_paths:
        if unreal.EditorAssetLibrary.save_asset(pkg, only_if_is_dirty=False):
            saved += 1
        else:
            notes.append("no se pudo guardar " + pkg)
    return saved, notes


def bounds_cm(mesh):
    b = mesh.get_bounds()  # BoxSphereBounds (sin verificar)
    o, e = b.origin, b.box_extent
    return ((o.x - e.x, o.y - e.y, o.z - e.z), (o.x + e.x, o.y + e.y, o.z + e.z))


def apply_scale(unreal, sub, mesh, s):
    bs = sub.get_lod_build_settings(mesh, 0)
    bs.build_scale3d = unreal.Vector(s, s, s)
    sub.set_lod_build_settings(mesh, 0, bs)


def apply_collision(unreal, sub, mesh, mode):
    sub.remove_collisions(mesh)
    if mode == "box":
        sub.add_simple_collisions(mesh, unreal.ScriptCollisionShapeType.BOX)
    elif mode == "convex":
        sub.set_convex_decomposition_collisions(mesh, 4, 16, 100000)  # envolventes convexas, vértices, precisión
    elif mode != "none":
        raise ValueError("colision desconocida: %s" % mode)
    if mode != "none" and sub.get_simple_collision_count(mesh) == 0:
        raise RuntimeError("la malla quedo sin colision simple")


def apply_lods(unreal, sub, mesh, n):
    opts = unreal.EditorScriptingMeshReductionOptions()
    opts.set_editor_property("auto_compute_lod_screen_size", True)
    settings = []
    for i in range(1, n + 1):
        st = unreal.EditorScriptingMeshReductionSettings()
        st.set_editor_property("percent_triangles", 0.5 ** i)
        st.set_editor_property("screen_size", 0.5 ** i)
        settings.append(st)
    opts.set_editor_property("reduction_settings", settings)
    sub.set_lods(mesh, opts)


def apply_nanite(sub, mesh):
    ns = sub.get_nanite_settings(mesh)
    ns.enabled = True
    sub.set_nanite_settings(mesh, ns, True)


def run():
    import unreal

    with open(os.environ["KIT_IMPORT_BATCH"], encoding="utf-8") as f:
        batch = json.load(f)
    defaults = batch.get("defaults", {})
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    report = []
    for raw in batch["items"]:
        item = dict(defaults, **raw)
        row = {"status": "OK", "asset": "", "source": item["source"], "scale": "", "notes": ""}
        notes = []
        try:
            if not os.path.isfile(item["source"]):
                raise FileNotFoundError(item["source"])
            name = rules.asset_name("static_mesh", item["base"], item.get("index"))
            bad = rules.validate_name(name, "static_mesh")
            if bad:
                raise ValueError("; ".join(bad))
            folder = rules.target_folder(item.get("origin", "own"), item.get("category", "Props"), item.get("pack"))
            paths = import_one(unreal, item["source"], folder, name)
            mesh_path, mesh = pick_static_mesh(unreal, paths)
            if mesh is None:
                raise RuntimeError("la importacion no produjo ningun StaticMesh")
            ren_notes, secondaries = rename_secondaries(unreal, paths, mesh_path, folder)
            notes += ren_notes
            mn, mx = bounds_cm(mesh)
            scale, why = rules.guess_scale([b - a for a, b in zip(mn, mx)], item.get("target_max_cm"))
            if abs(scale - 1.0) > 1e-6:
                apply_scale(unreal, sub, mesh, scale)
            mn, mx = bounds_cm(mesh)  # medir DESPUÉS de escalar
            size = [b - a for a, b in zip(mn, mx)]
            problem = rules.check_final_size(size, item.get("target_max_cm"))
            if problem:
                row["status"] = "FAIL"
                notes.append(problem)
            apply_collision(unreal, sub, mesh, item.get("collision", "convex"))
            if item.get("lods", 0) > 0:
                apply_lods(unreal, sub, mesh, int(item["lods"]))
            if item.get("nanite"):
                apply_nanite(sub, mesh)
            off = rules.pivot_offset(mn, mx, item.get("pivot", "bottom_center"))
            if max(abs(v) for v in off) > 1.0:
                if row["status"] == "OK":
                    row["status"] = "WARN"
                notes.append("pivote fuera del piso/centro, offset %s cm: corregir en el DCC o con Modeling Tools" % (tuple(round(v, 1) for v in off),))
            # Secundarios antes que la malla: la malla guardada no debe apuntar a paquetes sin guardar.
            to_save = secondaries + [mesh_path.split(".")[0]]
            saved, save_notes = save_packages(unreal, to_save)
            notes.append("guardados %d de %d paquetes" % (saved, len(to_save)))
            if save_notes:
                row["status"] = "FAIL"
                notes += save_notes
            row.update(asset=mesh_path, scale="%.4f (%s)" % (scale, why))
        except Exception as e:
            row["status"] = "FAIL"
            notes.append("excepcion: %r" % (e,))
        row["notes"] = "; ".join(notes)
        report.append(row)
        print("%s %s %s" % (row["status"], row["asset"] or row["source"], row["notes"]))
    default_out = os.path.join(str(unreal.Paths.project_saved_dir()), "asset-intake-report.csv")
    out = os.environ.get("KIT_IMPORT_REPORT", default_out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["status", "asset", "source", "scale", "notes"])
        w.writeheader()
        w.writerows(report)
    print("INFORME %s filas=%d" % (out, len(report)))
    return len(report) == len(batch["items"]) and not any(r["status"] == "FAIL" for r in report)


if __name__ == "__main__":
    try:
        ok = run()
    except Exception as e:
        print("KIT_FAIL excepcion: %r" % (e,))
        ok = False
    print("KIT_OK" if ok else "KIT_FAIL")
    sys.exit(0 if ok else 1)
