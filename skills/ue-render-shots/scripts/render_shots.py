"""Renders de presentación por el MCP de Epic (editor abierto con GPU). Reusa el cliente de ue-viewport-eyes.

Comandos:
  bounds <ruta_actor> [...] [--out subjects.json]
      Pide ActorTools.get_actor_bounds por cada actor y escribe sujetos {name, center, radius}.
      ruta_actor = ruta de objeto del actor, ej. /Game/Maps/Demo.Demo:PersistentLevel.SM_Avion_0
  capture <plan.json> --out <dir> [--min 1920x1080]
      Una CaptureViewport por toma (captureTransform de la toma, anotaciones apagadas, sin gizmos).
      Escribe <dir>/<toma>.png y <dir>/manifest.json con el tamaño real de cada imagen.
  highres <plan.json> --out <dir> [--res 1920x1080] [--script <archivo.py>]
      No captura: escribe el plan para editor_highres.py (camino de alta resolución, ver SKILL.md).

Salida de capture: "OK <png> <w>x<h>" por toma y al final RENDER_OK, RENDER_LOWRES (todas salieron
pero alguna mide menos que --min) o RENDER_FAIL. Códigos: 0 ok, 3 baja resolución, 1 fallo, 2 sin MCP.
"""
import importlib.util
import json
import math
import os
import sys
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ACTOR_TOOLS = "editor_toolset.toolsets.actor.ActorTools"


def load_client():
    path = os.path.normpath(os.path.join(HERE, "..", "..", "ue-viewport-eyes", "scripts", "ue_capture.py"))
    spec = importlib.util.spec_from_file_location("ue_capture", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------- puras ----------

def parse_res(text):
    try:
        w, h = (int(v) for v in text.lower().split("x"))
    except ValueError:
        raise ValueError("resolucion como 1920x1080: %r" % text)
    if w < 1 or h < 1:
        raise ValueError("resolucion positiva: %r" % text)
    return w, h


def subject_from_box(name, box):
    """Box de get_actor_bounds ({min:{x,y,z}, max:{x,y,z}}) -> sujeto con centro y media diagonal."""
    lo = [float(box["min"][k]) for k in "xyz"]
    hi = [float(box["max"][k]) for k in "xyz"]
    center = [round((a + b) / 2, 2) for a, b in zip(lo, hi)]
    radius = round(math.dist(lo, hi) / 2, 2)
    if radius <= 0:
        raise ValueError("%s: caja vacia (actor sin malla visible?)" % name)
    return {"name": name, "center": center, "radius": radius}


def actor_name(path):
    """Nombre corto y seguro para archivos desde la ruta del actor."""
    tail = path.rsplit(".", 1)[-1].rsplit(":", 1)[-1]
    return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in tail) or "actor"


def verdict(results, min_w, min_h):
    """results = [{name, ok, size:[w,h] o None}]. Devuelve (código, palabra)."""
    if not results or any(not r["ok"] for r in results):
        return 1, "RENDER_FAIL"
    if any(r["size"][0] < min_w or r["size"][1] < min_h for r in results):
        return 3, "RENDER_LOWRES"
    return 0, "RENDER_OK"


def highres_jobs(plan, out_dir, w, h):
    """Trabajos para editor_highres.py: cámara y comando HighResShot por toma (filename= verificado
    en GetHighResScreenShotInput de UnrealClient.cpp, UE 5.8)."""
    jobs = []
    for s in plan:
        png = os.path.join(out_dir, s["name"] + ".png").replace("\\", "/")
        jobs.append({"name": s["name"], "loc": s["loc"], "rot": s["rot"], "png": png,
                     "cmd": "HighResShot %dx%d filename=%s" % (w, h, png)})
    return jobs


# ---------- red ----------

def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def cmd_bounds(uc, mcp, argv):
    paths = [a for a in argv[2:] if a.startswith("/")]
    if not paths:
        print("FAIL falta al menos una ruta de actor")
        return 1
    subs = []
    for p in paths:
        box = mcp.call("get_actor_bounds", {"actor": {"refPath": p}}, ACTOR_TOOLS)
        subs.append(subject_from_box(actor_name(p), box))
        print("OK %s centro=%s radio=%s" % (p, subs[-1]["center"], subs[-1]["radius"]))
    data = {"subjects": subs, "shots": ["hero", "turntable:8", "lineup", "closeups"]}
    out = _arg(argv, "--out")
    text = json.dumps(data, indent=1)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)
    return 0


def cmd_capture(uc, mcp, argv):
    plan = json.load(open(argv[2], encoding="utf-8"))
    out = _arg(argv, "--out")
    min_w, min_h = parse_res(_arg(argv, "--min", "1920x1080"))
    os.makedirs(out, exist_ok=True)
    results = []
    for s in plan:
        png = os.path.join(out, s["name"] + ".png")
        try:
            w, h = uc.capture_viewport(mcp, png, s["loc"], s["rot"])
            results.append({"name": s["name"], "ok": True, "size": [w, h], "png": png})
        except (ValueError, urllib.error.URLError, OSError) as e:
            print("FAIL %s: %s" % (s["name"], e))
            results.append({"name": s["name"], "ok": False, "size": None, "png": png})
    code, word = verdict(results, min_w, min_h)
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"min": [min_w, min_h], "result": word, "shots": results}, f, indent=1)
    if code == 3:
        print("Alguna toma mide menos de %dx%d (CaptureViewport usa el tamano del viewport). "
              "Maximizar el viewport o usar el camino de alta resolucion (highres)." % (min_w, min_h))
    print(word)
    return code


def cmd_highres(argv):
    plan = json.load(open(argv[2], encoding="utf-8"))
    out = os.path.abspath(_arg(argv, "--out"))
    w, h = parse_res(_arg(argv, "--res", "1920x1080"))
    jobs_path = os.path.join(out, "highres-jobs.json")
    os.makedirs(out, exist_ok=True)
    with open(jobs_path, "w", encoding="utf-8") as f:
        json.dump(highres_jobs(plan, out, w, h), f, indent=1)
    script = os.path.join(HERE, "editor_highres.py").replace("\\", "/")
    print("JOBS %s" % jobs_path)
    print("En la consola de Python del editor (la teclea la persona):")
    print('  py "%s" "%s"' % (script, jobs_path.replace("\\", "/")))
    return 0


def main(argv):
    if len(argv) < 3 or argv[1] not in ("bounds", "capture", "highres"):
        print(__doc__)
        return 1
    if argv[1] in ("capture", "highres") and not _arg(argv, "--out"):
        print("FAIL falta --out")
        return 1
    try:
        if argv[1] == "highres":
            return cmd_highres(argv)
        uc = load_client()
        mcp = uc.Mcp()
        try:
            mcp.ping()
        except (urllib.error.URLError, OSError) as e:
            print("FAIL no responde el MCP en %s (%s). Correr ue-session-preflight." % (mcp.url, e))
            return 2
        return cmd_bounds(uc, mcp, argv) if argv[1] == "bounds" else cmd_capture(uc, mcp, argv)
    except (ValueError, KeyError, OSError) as e:
        print("FAIL %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
