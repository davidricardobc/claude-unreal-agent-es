"""import_audio.py: plantilla para importar los WAV de final/ a /Game/Audio/<Categoria>/ (Python del editor de UE 5.8).

Lee final/import-list.json (lo escribe postprocess.mjs). Por cada toma:
  1. AssetImportTask con SoundFactory, nombre fijo SW_<Categoria>_<Id>_<NN> y replace_existing (reimportar no duplica).
  2. Carga el asset importado con load_asset y fija looping, clase de sonido, atenuación y concurrencia.
  3. Guarda solo lo que cambió y escribe import-report.json con lo que falló.
Nunca crea un SoundWave() nuevo (no funciona) ni Sound Cues (la creación automática falla en Python).

Uso (con el editor abierto, por la consola de Python o por MCP):
  py "C:/ruta/import_audio.py" "C:/ruta/AudioSource/audio-work/final"
Sin editor (sin interfaz):
  UnrealEditor-Cmd.exe <Proyecto>.uproject -ExecutePythonScript="C:/ruta/import_audio.py C:/ruta/final"
Variables opcionales: AUDIO_FINAL_DIR (en vez del argumento), AUDIO_FORCE=1 (reimportar todo aunque no cambie).
"""
import hashlib
import json
import os
import sys

import unreal

GAME_ROOT = "/Game/Audio"
CLASS_DIR = f"{GAME_ROOT}/Classes"
ATT_DIR = f"{GAME_ROOT}/Attenuation"
CONC_DIR = f"{GAME_ROOT}/Concurrency"

# Atenuación 3D por categoría, en cm de Unreal. None = sonido 2D (sin atenuación): interfaz, música, locutor.
# Valores de partida: ajustarlos a la escala de la mesa del juego (sin verificar en 5.8).
DEFAULT_ATT = {"inner": 300.0, "falloff": 6000.0, "lpf": True}
ATTENUATION = {
    "UI": None,
    "Mus": None,
    "VO": None,
    "Amb": {"inner": 1500.0, "falloff": 20000.0, "lpf": False},
}
# Volumen de la Sound Class por categoría (1.0 si no aparece).
CLASS_VOLUME = {"UI": 0.8, "Mus": 0.7, "Amb": 0.8}
# Concurrencia por categoría: máximo de voces y regla al pasarse (MaxConcurrentResolutionRule existe en 5.8).
CONCURRENCY = {"Eng": {"max": 10, "rule": "STOP_FARTHEST_THEN_OLDEST"}}

FORCE = os.environ.get("AUDIO_FORCE") == "1"


def final_dir():
    d = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AUDIO_FINAL_DIR", "")
    if not d or not os.path.isdir(d):
        raise RuntimeError("Pasa la carpeta final/ como argumento o en AUDIO_FINAL_DIR (donde esta import-list.json).")
    return d


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_set(obj, prop, value, warnings):
    """set_editor_property sin romper el lote: anota el nombre de propiedad que no existe en esta versión."""
    try:
        obj.set_editor_property(prop, value)
        return True
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"{type(obj).__name__}.{prop}: {exc}")
        return False


def ensure_asset(folder, name, asset_class, factory):
    path = f"{folder}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.EditorAssetLibrary.load_asset(path)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, asset_class, factory)


def sound_class(cat, warnings):
    sc = ensure_asset(CLASS_DIR, f"SC_{cat}", unreal.SoundClass, unreal.SoundClassFactory())
    if sc and cat in CLASS_VOLUME:
        props = sc.get_editor_property("properties")
        if safe_set(props, "volume", CLASS_VOLUME[cat], warnings):
            safe_set(sc, "properties", props, warnings)
    return sc


def attenuation(cat, warnings):
    cfg = ATTENUATION.get(cat, DEFAULT_ATT)
    if cfg is None:
        return None
    sa = ensure_asset(ATT_DIR, f"SA_{cat}", unreal.SoundAttenuation, unreal.SoundAttenuationFactory())
    if not sa:
        return None
    att = sa.get_editor_property("attenuation")
    safe_set(att, "attenuate", True, warnings)
    safe_set(att, "spatialize", True, warnings)
    safe_set(att, "attenuation_shape", unreal.AttenuationShape.SPHERE, warnings)
    safe_set(att, "attenuation_shape_extents", unreal.Vector(cfg["inner"], 0.0, 0.0), warnings)
    safe_set(att, "falloff_distance", cfg["falloff"], warnings)
    safe_set(att, "attenuate_with_lpf", cfg["lpf"], warnings)
    if cfg["lpf"]:
        safe_set(att, "lpf_radius_min", cfg["inner"], warnings)
        safe_set(att, "lpf_radius_max", cfg["falloff"], warnings)
    safe_set(sa, "attenuation", att, warnings)
    return sa


def concurrency(cat, warnings):
    cfg = CONCURRENCY.get(cat)
    if not cfg:
        return None
    sc = ensure_asset(CONC_DIR, f"SCON_{cat}", unreal.SoundConcurrency, unreal.SoundConcurrencyFactory())
    if not sc:
        return None
    settings = sc.get_editor_property("concurrency")
    safe_set(settings, "max_count", cfg["max"], warnings)
    safe_set(settings, "resolution_rule", getattr(unreal.MaxConcurrentResolutionRule, cfg["rule"]), warnings)
    safe_set(sc, "concurrency", settings, warnings)
    return sc


def main():
    root = final_dir()
    with open(os.path.join(root, "import-list.json"), encoding="utf-8") as f:
        items = json.load(f)
    state_path = os.path.join(root, "import-state.json")
    state = json.load(open(state_path, encoding="utf-8")) if os.path.exists(state_path) else {}
    report = {"imported": [], "unchanged": [], "failed": [], "warnings": []}
    lib = unreal.EditorAssetLibrary

    # 1) Importar solo lo nuevo o cambiado (el nombre fijo + replace_existing evita duplicados).
    tasks, todo = [], []
    for it in items:
        src = os.path.join(root, it["file"])
        dest = f"{GAME_ROOT}/{it['categoria']}"
        digest = sha1(src) if os.path.exists(src) else None
        if digest is None:
            report["failed"].append({"asset": it["asset"], "error": f"no existe {src}"})
            continue
        if not FORCE and state.get(it["asset"]) == digest and lib.does_asset_exist(f"{dest}/{it['asset']}"):
            report["unchanged"].append(it["asset"])
            continue
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", src)
        task.set_editor_property("destination_path", dest)
        task.set_editor_property("destination_name", it["asset"])
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("automated", True)
        task.set_editor_property("save", True)
        task.set_editor_property("factory", unreal.SoundFactory())
        tasks.append(task)
        todo.append((it, digest))
    if tasks:
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    for task, (it, _) in zip(tasks, todo):
        if not task.get_editor_property("imported_object_paths"):
            report["failed"].append({"asset": it["asset"], "error": "la importacion no devolvio ningun objeto"})

    # 2) Propiedades: se aplican a todo (también a lo sin cambios) para que un cambio de la tabla de arriba llegue a los assets.
    cache = {}
    digests = {i["asset"]: d for i, d in todo}
    failed_names = {f["asset"] for f in report["failed"]}
    for it in items:
        path = f"{GAME_ROOT}/{it['categoria']}/{it['asset']}"
        if not lib.does_asset_exist(path):
            if not any(f["asset"] == it["asset"] for f in report["failed"]):
                report["failed"].append({"asset": it["asset"], "error": "no quedo importado"})
            continue
        cat = it["categoria"]
        w = report["warnings"]
        if cat not in cache:
            cache[cat] = (sound_class(cat, w), attenuation(cat, w), concurrency(cat, w))
        sc, sa, con = cache[cat]
        wave = lib.load_asset(path)  # nunca SoundWave(): hay que cargar el importado
        safe_set(wave, "looping", bool(it["loop"]), w)
        if sc:
            safe_set(wave, "sound_class_object", sc, w)
        if sa:
            safe_set(wave, "attenuation_settings", sa, w)
        if con:
            safe_set(wave, "concurrency_set", {con}, w)
        for a in (wave, sc, sa, con):
            if a:
                lib.save_loaded_asset(a)  # guarda solo si cambió
        if it["asset"] in digests and it["asset"] not in failed_names:
            state[it["asset"]] = digests[it["asset"]]
            report["imported"].append(it["asset"])

    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    with open(os.path.join(root, "import-report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    unreal.log(f"Audio: {len(report['imported'])} importados, {len(report['unchanged'])} sin cambios, {len(report['failed'])} fallaron.")
    for msg in sorted(set(report["warnings"])):
        unreal.log_warning(f"Propiedad no aplicada (nombre distinto en esta version?): {msg}")
    for fail in report["failed"]:
        unreal.log_error(f"{fail['asset']}: {fail['error']}")
    return not report["failed"]


if __name__ == "__main__":
    # ue-headless/run-python.ps1 decide el éxito por la línea KIT_OK.
    try:
        ok = main()
    except Exception as e:  # noqa: BLE001
        print("KIT_FAIL excepcion: %r" % (e,))
        ok = False
    print("KIT_OK" if ok else "KIT_FAIL")
