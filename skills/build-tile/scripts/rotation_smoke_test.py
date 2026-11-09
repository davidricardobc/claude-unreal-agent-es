"""Prueba de giro 0/90/180/270 de una loseta (Python de editor de UE 5.8).

Por cada giro q (0, 90, 180, 270):
  (1) BORDES (pura): la loseta girada q debe encajar con una copia girada r, para todo r,
      en los dos ejes (E con W, N con S). Con rotatable=true esto exige 4 bordes iguales.
  (2) COLISIÓN (PIE): en un mapa de prueba vacío se ponen 4 Level Instances de la loseta (yaw 0/90/180/270),
      se juega en PIE, se trazan rayos hacia abajo en 5 puntos por borde (rotados con el mismo yaw)
      y se exige colisión a la altura esperada. Al final se borran las instancias (ver run_async).
Imprime PASS/FAIL por cada giro y KIT_OK solo si los 4 pasan; KIT_FAIL si no.

Entorno: KIT_TILE_MANIFEST (JSON), KIT_TEST_MAP (mapa vacío, ej. /Game/Maps/L_TileTest),
KIT_TILE_TOL_CM (default 50) y KIT_TILE_PIE_WAIT_S (segundos de espera en PIE para que carguen las instancias, default 4).
Parte pura sin UE:  python rotation_smoke_test.py --pure manifiesto.json
Verificado en UE 5.8.4 (proyecto C++ en blanco, 9-nov-2026: 4/4 giros). Sin probar: un build empaquetado
y la colisión de Landscape en niveles girados (reportada como frágil, evidencia floja).
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate_tile_manifest as vtm  # noqa: E402


def edge_fails_for_rotation(m, q):
    """Pura. Fallos de encaje de la loseta girada q contra copias giradas r=0..3."""
    fails = []
    for r in range(4):
        a = vtm.rotate_edges(m["edges"], q)
        b = vtm.rotate_edges(m["edges"], r)
        for sa, sb in (("E", "W"), ("N", "S")):
            if vtm.edge_key(a[sa]) != vtm.edge_key(b[sb]):
                fails.append("giro %d con vecina a %d: %s(%s) no encaja con %s(%s)" % (
                    q * 90, r * 90, sa, vtm.edge_key(a[sa]), sb, vtm.edge_key(b[sb])))
    return fails


def rotate_point(x, y, yaw_deg):
    """Gira (x, y) alrededor del origen yaw grados (sentido de UE: yaw positivo = horario visto desde arriba, con Y hacia abajo)."""
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    return (x * c - y * s, x * s + y * c)


def trace_points(m, yaw_deg, ts=(-0.8, -0.4, 0.0, 0.4, 0.8)):
    """Pura. [(lado_original, x, y, z_esperado)] ya rotados por yaw."""
    half = m["size_cm"][0] / 2.0
    out = []
    for side, e in m["edges"].items():
        for t in ts:
            x, y = {"N": (t * half, half - 1), "S": (t * half, -half + 1),
                    "E": (half - 1, t * half), "W": (-half + 1, t * half)}[side]
            rx, ry = rotate_point(x, y, yaw_deg)
            out.append((side, rx, ry, e["height_cm"]))
    return out


def with_retries(fn, tries=3, between=None):
    """Pura. Llama fn() hasta que devuelva algo distinto de None, máximo `tries` veces.
    Entre intentos llama between() (esperar o dejar que el editor cargue). Devuelve (valor, intentos)."""
    tries = max(1, int(tries))
    for i in range(1, tries + 1):
        v = fn()
        if v is not None:
            return v, i
        if between is not None and i < tries:
            between()
    return None, tries


def hit_z(result):
    """Z del impacto o None. Acepta (bool, HitResult) o un HitResult.
    Verificado en UE 5.8.4: un struct HitResult se ve como falso al evaluarlo y sus campos no se pueden leer con get_editor_property,
    lo que hacía que toda traza pareciera "sin colisión". to_tuple() funciona: [0] = impacto bloqueante, el primer Vector = ubicación."""
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], bool):
        if not result[0]:
            return None
        result = result[1]
    try:
        t = result.to_tuple()
    except Exception:
        return None
    if not t or not t[0]:
        return None
    for v in t[1:]:
        if hasattr(v, "z") and hasattr(v, "x"):
            return v.z
    return None


def collision_fails(unreal, m, yaw, tol):
    """Crea el Level Instance girado, traza y lo destruye. Sin verificar en 5.8."""
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    li = actors.spawn_actor_from_class(unreal.LevelInstance, unreal.Vector(0, 0, 0),
                                       unreal.Rotator(0.0, 0.0, float(yaw)))
    if li is None:
        return ["no se pudo crear el LevelInstance"]
    fails = []
    try:
        # Verificado en 5.8.4 (ronda 8 de TableFlyer): set_editor_property("world_asset") NO carga el nivel y
        # time.sleep bloquea el hilo del editor, así que nunca había colisión. Hay que llamar
        # set_world_asset + load_level_instance (UFUNCTION expuestas) y revisar is_loaded.
        li.set_world_asset(unreal.EditorAssetLibrary.load_asset(m["level"]))
        li.load_level_instance()
        if not li.is_loaded():
            return ["el Level Instance no cargo (load_level_instance)"]
        tries = int(os.environ.get("KIT_TILE_TRACE_TRIES", "3"))
        wait = float(os.environ.get("KIT_TILE_TRACE_WAIT_S", "1.0"))
        for side, x, y, z_exp in trace_points(m, yaw):
            def trace(x=x, y=y):
                return hit_z(unreal.SystemLibrary.line_trace_single(
                    world, unreal.Vector(x, y, 100000.0), unreal.Vector(x, y, -100000.0),
                    unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [],
                    unreal.DrawDebugTrace.NONE, True))
            z, n = with_retries(trace, tries, lambda: time.sleep(wait))
            if z is None:
                fails.append("%s (%.0f,%.0f): sin colision tras %d intentos (repetir en PIE)" % (side, x, y, n))
            elif abs(z - z_exp) > tol:
                fails.append("%s (%.0f,%.0f): z=%.1f esperado %s" % (side, x, y, z, z_exp))
    finally:
        actors.destroy_actor(li)
    return fails


def main(argv):
    path = os.environ.get("KIT_TILE_MANIFEST") or next((a for a in argv[1:] if not a.startswith("--")), None)
    if not path:
        print("KIT_FAIL falta KIT_TILE_MANIFEST")
        return False
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    unreal = None
    tol = float(os.environ.get("KIT_TILE_TOL_CM", "50"))
    if "--pure" not in argv:
        import unreal
        test_map = os.environ.get("KIT_TEST_MAP")
        if not test_map:
            print("KIT_FAIL falta KIT_TEST_MAP (mapa vacio de prueba)")
            return False
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(test_map)
    if unreal is not None:
        # El Level Instance carga en ticks del editor: la prueba de colisión corre por callback (resultado al final
        # en el log). main devuelve True solo para "arrancado".
        run_async(unreal, m, tol)
        return True
    all_ok = True
    for q in range(4):
        fails = edge_fails_for_rotation(m, q) if m.get("rotatable", True) else []
        for t in fails:
            print("  - " + t)
        print("%s giro %d" % ("FAIL" if fails else "PASS", q * 90))
        all_ok = all_ok and not fails
    print("KIT_OK" if all_ok else "KIT_FAIL")
    return all_ok


def run_async(unreal, m, tol, max_wait_s=60.0):
    """Prueba de colisión en PIE (verificada en UE 5.8.4 en un proyecto C++ en blanco y en TableFlyer).
    Por qué PIE: en el mundo del EDITOR las trazas de línea no chocan con la geometría de un Level Instance aunque ya haya cargado; en PIE sí.
    Pasos (una máquina de estados en register_slate_post_tick_callback, para que el editor siga haciendo tick):
      1. poner 4 Level Instances de la loseta en el mapa de prueba, lado a lado, girados 0/90/180/270, y guardar;
      2. iniciar PIE y esperar a que exista el mundo de juego y hayan pasado unos cuadros;
      3. trazar los puntos de borde de cada loseta en el mundo de juego e imprimir PASS/FAIL por giro;
      4. detener PIE, borrar las 4 instancias y volver a guardar el mapa de prueba. Al final imprime KIT_OK o KIT_FAIL."""
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    spacing = float(m["size_cm"][0]) * 3.0
    tile = unreal.EditorAssetLibrary.load_asset(m["level"])
    if tile is None:
        print("KIT_FAIL no existe el nivel de la loseta %s" % m["level"])
        return
    for a in actors.get_all_level_actors():  # restos de una corrida abortada
        if a.get_actor_label().startswith("TileSmoke_"):
            actors.destroy_actor(a)
    for q in range(4):
        li = actors.spawn_actor_from_class(unreal.LevelInstance, unreal.Vector(q * spacing, 0, 0), unreal.Rotator(0.0, 0.0, q * 90.0))
        li.set_actor_label("TileSmoke_%d" % (q * 90))
        li.set_world_asset(tile)
        li.load_level_instance()
    les.save_current_level()
    st = {"phase": "start", "t": 0.0, "frames": 0, "handle": None, "ok": True}

    def trace(world, x, y):
        return hit_z(unreal.SystemLibrary.line_trace_single(
            world, unreal.Vector(x, y, 100000.0), unreal.Vector(x, y, -100000.0),
            unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True))

    def cleanup():
        for a in actors.get_all_level_actors():
            if a.get_actor_label().startswith("TileSmoke_"):
                actors.destroy_actor(a)
        les.save_current_level()

    def tick(dt):
        st["t"] += dt
        if st["phase"] == "start":
            les.editor_request_begin_play()
            st["phase"], st["t"] = "wait", 0.0
            return
        if st["phase"] == "wait":
            world = ues.get_game_world()
            if world is None:
                if st["t"] > max_wait_s:
                    print("KIT_FAIL PIE no arranco en %.0f s" % max_wait_s)
                    st["phase"] = "end"
                return
            st["frames"] += 1
            if st["frames"] == 1:
                st["t"] = 0.0
            if st["t"] < float(os.environ.get("KIT_TILE_PIE_WAIT_S", "4")):  # dejar que las instancias carguen por streaming
                return
            for q in range(4):
                fails = edge_fails_for_rotation(m, q) if m.get("rotatable", True) else []
                for side, x, y, z_exp in trace_points(m, q * 90):
                    z = trace(world, x + q * spacing, y)
                    if z is None:
                        fails.append("colision %s (%.0f,%.0f): sin colision" % (side, x, y))
                    elif abs(z - z_exp) > tol:
                        fails.append("colision %s (%.0f,%.0f): z=%.1f esperado %s" % (side, x, y, z, z_exp))
                for t in fails:
                    print("  - " + t)
                print("%s giro %d" % ("FAIL" if fails else "PASS", q * 90))
                st["ok"] = st["ok"] and not fails
            les.editor_request_end_play()
            st["phase"], st["t"] = "stopping", 0.0
            return
        if st["phase"] == "stopping":
            if ues.get_game_world() is not None and st["t"] < 15:
                return
            st["phase"] = "end"
        if st["phase"] == "end":
            unreal.unregister_slate_post_tick_callback(st["handle"])
            cleanup()
            print("KIT_OK" if st["ok"] else "KIT_FAIL")

    st["handle"] = unreal.register_slate_post_tick_callback(tick)
    print("KIT_INFO prueba de colision en PIE en marcha (4 giros); el resultado sale en el log")


if __name__ == "__main__":
    try:
        sys.exit(0 if main(sys.argv) else 1)
    except Exception as e:
        print("KIT_FAIL excepcion: %r" % (e,))
        sys.exit(1)
