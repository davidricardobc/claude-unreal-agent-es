"""Guiones de maniobras: carga JSON/CSV y devuelve el stick virtual en el tiempo t.

Puro (sin Unreal): se puede probar con `python -m unittest`.
Stick: dict con throttle (0..1), pitch, roll, yaw (-1..1). Convención: pitch +1 = nariz arriba.
"""
import csv
import json

NEUTRAL = {"throttle": 0.0, "pitch": 0.0, "roll": 0.0, "yaw": 0.0}
STICK_KEYS = tuple(NEUTRAL)


def load_maneuvers(path):
    """JSON: {"maneuvers":[{id, duration_s, setup, steps:[{t0,t1,stick}], criteria}]}.
    CSV (solo pasos): id,t0,t1,throttle,pitch,roll,yaw. Los criterios van en un JSON aparte."""
    if path.lower().endswith(".csv"):
        by_id = {}
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                m = by_id.setdefault(row["id"], {"id": row["id"], "steps": [], "criteria": {}})
                m["steps"].append({
                    "t0": float(row["t0"]), "t1": float(row["t1"]),
                    "stick": {k: float(row.get(k) or 0.0) for k in STICK_KEYS},
                })
        out = list(by_id.values())
        for m in out:
            m["duration_s"] = max(s["t1"] for s in m["steps"])
        return out
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)["maneuvers"]


def stick_at(maneuver, t):
    """Stick activo en t. Si varios pasos se solapan, gana el último.
    Fuera de todos los pasos: ejes neutros y el gas del último paso ya iniciado."""
    steps = maneuver["steps"]
    active = None
    last_throttle = 0.0
    for s in steps:
        if s["t0"] <= t:
            last_throttle = {**NEUTRAL, **s["stick"]}["throttle"]
        if s["t0"] <= t < s["t1"]:
            active = {**NEUTRAL, **s["stick"]}
    if active is None:
        active = dict(NEUTRAL)
        active["throttle"] = last_throttle
    return active


def validate(maneuver):
    """Devuelve lista de problemas (vacía si está bien)."""
    errs = []
    if not maneuver.get("id"):
        errs.append("falta id")
    if not maneuver.get("steps"):
        errs.append("sin pasos")
    for i, s in enumerate(maneuver.get("steps", [])):
        if s["t1"] <= s["t0"]:
            errs.append("paso %d: t1 <= t0" % i)
        for k, v in s.get("stick", {}).items():
            if k not in STICK_KEYS:
                errs.append("paso %d: eje desconocido %s" % (i, k))
            elif not -1.0 <= v <= 1.0:
                errs.append("paso %d: %s fuera de rango" % (i, k))
    return errs
