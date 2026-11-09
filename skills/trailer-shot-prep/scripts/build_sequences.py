"""Crea un Level Sequence con CineCamera por cada toma del CSV. Corre DENTRO de Unreal (Python de editor).
Verificado en UE 5.8.4 (proyecto C++ en blanco y TableFlyer, 9-nov-2026; ver SKILL.md, "Estado"). Sin verificar: lo marcado SV
(la búsqueda del actor `target` y el orden de los canales de la transformación).

Uso (wrapper de ue-headless, que busca KIT_OK):
  powershell -File .claude/skills/ue-headless/scripts/run-python.ps1 -UERoot "<UE_ROOT>" -Project "<ProyectoDir>\\<Proyecto>.uproject" -Script ".claude/skills/trailer-shot-prep/scripts/build_sequences.py"
Variables de entorno:
  KIT_TRAILER_SHOTS    ruta del CSV de tomas (obligatoria)
  KIT_TRAILER_RADIUS   distancia de trabajo en cm (por defecto 1500)
  KIT_TRAILER_MIN_S / KIT_TRAILER_MAX_S   rango de duración total (por defecto 30 y 60)
  KIT_TRAILER_REBUILD  1 = recrear las secuencias que ya existen (si no, se saltan aunque el CSV haya cambiado)
Crea /Game/Cine/Trailer/LS_<NN>_<momento>. La cámara es spawnable: no se toca el mapa. Cada mapa se carga una sola vez.
Guarda solo las secuencias creadas. KIT_OK solo si todas las tomas quedaron bien.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shot_plan  # noqa: E402


def get_actors(unreal):
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)  # SV
    return sub.get_all_level_actors()


def load_level(unreal, path):
    ok = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(path)
    if ok is False:
        raise RuntimeError("load_level devolvió False")


def binding_ok(binding):
    """Pura. Un FMovieSceneBindingProxy sirve si existe y is_valid() (ScriptMethod de
    MovieSceneBindingExtensions) da True. Objetos sin is_valid se aceptan si no son None."""
    if binding is None:
        return False
    check = getattr(binding, "is_valid", None)
    if check is None:
        return True
    try:
        return bool(check())
    except Exception:
        return False


def add_camera_spawnable(unreal, seq):
    """CineCamera spawnable. Devuelve (binding, camino).

    Verificado en el código de UE 5.8:
    - LevelSequenceEditorSubsystem.add_spawnable_from_class exige la secuencia ABIERTA en
      Sequencer (GetActiveSequencer; si no, loguea "requires that the requested sequence be open
      in the editor" y devuelve un proxy vacío). En commandlet (run-python.ps1) nunca hay Sequencer.
    - seq.add_spawnable_from_class (MovieSceneSequenceExtensions) está deprecada desde 5.5 pero
      existe en 5.8 y no necesita Sequencer. Por eso va primero.
    Cada camino se valida con binding_ok; si ninguno da un binding válido, falla la toma."""
    tried = []
    if hasattr(seq, "add_spawnable_from_class"):
        b = seq.add_spawnable_from_class(unreal.CineCameraActor)
        if binding_ok(b):
            return b, "secuencia (deprecada, sin Sequencer)"
        tried.append("secuencia")
    sub = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
    if sub is not None and hasattr(sub, "add_spawnable_from_class"):
        b = sub.add_spawnable_from_class(seq, unreal.CineCameraActor)
        if binding_ok(b):
            return b, "subsistema (Sequencer abierto)"
        tried.append("subsistema (necesita la secuencia abierta en Sequencer)")
    raise RuntimeError("no se pudo crear la camara spawnable; probado: " + ", ".join(tried or ["nada"]))


def find_center(unreal, label):
    """Centro de la toma: ubicación del actor con esa etiqueta, o el origen si no hay o no se encuentra."""
    if not label:
        return (0.0, 0.0, 0.0)
    for a in get_actors(unreal):
        if a.get_actor_label() == label:
            loc = a.get_actor_location()
            return (loc.x, loc.y, loc.z)
    print("KIT_WARN actor '%s' no encontrado; uso el origen" % label)
    return (0.0, 0.0, 0.0)


def build_one(unreal, shot, radius, rebuild):
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    path = shot["seq_path"]
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        if not rebuild:
            print("KIT_INFO existe, se salta (KIT_TRAILER_REBUILD=1 para recrear):", path)
            return
        unreal.EditorAssetLibrary.delete_asset(path)
    center = find_center(unreal, shot["target"])  # el mapa de la toma ya está cargado
    keys = shot_plan.camera_keys(shot["camera_type"], center, radius, shot["duration_s"], shot_plan.FPS)

    seq = tools.create_asset(shot["seq_name"], shot_plan.SEQ_DIR, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
    seq.set_display_rate(unreal.FrameRate(shot_plan.FPS, 1))
    seq.set_playback_start(0)
    seq.set_playback_end(shot["frames"])

    cam, how = add_camera_spawnable(unreal, seq)
    print("KIT_INFO camara por %s" % how)
    cam.set_name("TrailerCam")

    cut_track = seq.add_track(unreal.MovieSceneCameraCutTrack)
    cut = cut_track.add_section()
    cut.set_range(0, shot["frames"])
    cut.set_camera_binding_id(seq.get_binding_id(cam))  # make_binding_id no existe en 5.x (verificado en 5.8.4)

    # Transformación por claves. Orden de canales (SV): loc X,Y,Z, rot X=roll, Y=pitch, Z=yaw, scale X,Y,Z
    tr = cam.add_track(unreal.MovieScene3DTransformTrack)
    sec = tr.add_section()
    sec.set_range(0, shot["frames"])
    # 5.8.4: get_channels() ya no existe (verificado, ronda 8 de TableFlyer); get_all_channels() da los 9 canales.
    ch = sec.get_all_channels() if hasattr(sec, "get_all_channels") else sec.get_channels()
    for k in keys:
        f = unreal.FrameNumber(k["frame"])
        x, y, z = k["loc"]
        pitch, roll, yaw = k["rot"]
        for idx, val in ((0, x), (1, y), (2, z), (3, roll), (4, pitch), (5, yaw)):
            ch[idx].add_key(f, val)
    unreal.EditorAssetLibrary.save_asset(path)
    print("KIT_INFO secuencia creada: %s (%d claves)" % (path, len(keys)))


def main():
    try:
        import unreal
    except ImportError:
        print("KIT_FAIL este script corre dentro de Unreal (usa shot_plan.py check para validar fuera)")
        return 1
    csv_path = os.environ.get("KIT_TRAILER_SHOTS")
    if not csv_path or not os.path.exists(csv_path):
        print("KIT_FAIL falta KIT_TRAILER_SHOTS")
        return 1
    shots = shot_plan.load_shots(csv_path)
    errs, warns = shot_plan.validate(shots, float(os.environ.get("KIT_TRAILER_MIN_S", "30")),
                                     float(os.environ.get("KIT_TRAILER_MAX_S", "60")))
    for w in warns:
        print("KIT_WARN", w)
    if errs:
        print("KIT_FAIL plan inválido: " + "; ".join(errs))
        return 1
    radius = float(os.environ.get("KIT_TRAILER_RADIUS", "1500"))
    rebuild = os.environ.get("KIT_TRAILER_REBUILD") == "1"
    by_map = {}
    for s in shots:
        by_map.setdefault(s["map"], []).append(s)
    failed = 0
    for map_path, group in by_map.items():
        try:
            load_level(unreal, map_path)
        except Exception as e:
            failed += len(group)
            print("KIT_FAIL no se pudo cargar %s: %s" % (map_path, e))
            continue
        for s in group:
            try:
                build_one(unreal, s, radius, rebuild)
            except Exception as e:  # una toma mala no tumba las demás
                failed += 1
                print("KIT_FAIL toma %s: %s" % (s["seq_name"], e))
    if failed:
        return 1
    print("KIT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
