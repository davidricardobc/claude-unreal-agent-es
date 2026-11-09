"""Camino de alta resolución: corre DENTRO del editor abierto, desde su consola de Python.

  py "<ruta>/editor_highres.py" "<dir>/highres-jobs.json"

Por qué así: el MCP de Epic no trae herramienta de consola (EditorAppToolset.h de 5.8) y
execute_tool_script es un sandbox sin import unreal; run-python.ps1 corre sin GPU. La persona
teclea una línea y el script hace el resto.

Por cada toma: mueve la cámara del viewport (UnrealEditorSubsystem.set_level_viewport_camera_info),
espera unos cuadros, manda "HighResShot WxH filename=<png>" (ExecuteConsoleCommand) y espera a que
el PNG exista antes de seguir. Lo encadena con register_slate_post_tick_callback para no bloquear
el editor. Al final imprime RENDER_HIGHRES_OK o RENDER_HIGHRES_FAIL en el Output Log.
API verificada en headers de 5.8 (UnrealEditorSubsystem.h, KismetSystemLibrary.h, PySlate.cpp,
UnrealClient.cpp); el ciclo completo está SIN VERIFICAR en la máquina: probar con 1 toma.
Antes: Game View (tecla G en el viewport) para que no salgan íconos ni cajas de triggers.
"""
import json
import os
import sys

SETTLE_TICKS = 20      # cuadros entre mover la cámara y disparar (streaming y exposición)
TIMEOUT_TICKS = 1800   # ~30 s a 60 fps por toma antes de darla por fallida


def next_step(state, png_exists):
    """Pura. Máquina de estados por toma: 'move' -> 'settle' -> 'shoot' -> 'wait' -> siguiente.
    state = {"i", "phase", "ticks"}; devuelve (state_nuevo, acción) con acción en
    move | shoot | done_ok | done_fail | None."""
    i, phase, ticks = state["i"], state["phase"], state["ticks"]
    if phase == "move":
        return {"i": i, "phase": "settle", "ticks": 0}, "move"
    if phase == "settle":
        if ticks + 1 >= SETTLE_TICKS:
            return {"i": i, "phase": "wait", "ticks": 0}, "shoot"
        return {"i": i, "phase": "settle", "ticks": ticks + 1}, None
    if phase == "wait":
        if png_exists:
            return {"i": i + 1, "phase": "move", "ticks": 0}, "done_ok"
        if ticks + 1 >= TIMEOUT_TICKS:
            return {"i": i + 1, "phase": "move", "ticks": 0}, "done_fail"
        return {"i": i, "phase": "wait", "ticks": ticks + 1}, None
    raise ValueError("fase desconocida: " + phase)


def run(jobs_path):
    import unreal

    jobs = json.load(open(jobs_path, encoding="utf-8"))
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    for j in jobs:
        if os.path.exists(j["png"]):
            os.remove(j["png"])  # para saber que el PNG es de esta corrida
    st = {"state": {"i": 0, "phase": "move", "ticks": 0}, "ok": 0, "fail": [], "handle": None}

    def tick(_dt):
        s = st["state"]
        if s["i"] >= len(jobs):
            unreal.unregister_slate_post_tick_callback(st["handle"])
            word = "RENDER_HIGHRES_OK" if not st["fail"] else "RENDER_HIGHRES_FAIL " + ",".join(st["fail"])
            unreal.log("%s %d/%d" % (word, st["ok"], len(jobs)))
            return
        j = jobs[s["i"]]
        new, action = next_step(s, os.path.exists(j["png"]))
        if action == "move":
            pitch, yaw, roll = j["rot"]
            ues.set_level_viewport_camera_info(unreal.Vector(*j["loc"]),
                                               unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw))
        elif action == "shoot":
            unreal.SystemLibrary.execute_console_command(None, j["cmd"])
        elif action == "done_ok":
            st["ok"] += 1
            unreal.log("OK " + j["png"])
        elif action == "done_fail":
            st["fail"].append(j["name"])
            unreal.log_error("sin PNG tras esperar: " + j["name"])
        st["state"] = new

    st["handle"] = unreal.register_slate_post_tick_callback(tick)
    unreal.log("RENDER_HIGHRES empieza: %d tomas" % len(jobs))


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else os.environ["RENDER_JOBS"])
