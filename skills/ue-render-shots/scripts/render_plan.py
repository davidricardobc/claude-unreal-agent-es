"""Plan de tomas de presentación (puro, sin Unreal): hero, turntable, lineup, closeups y tomas a mano.

Entrada (JSON, ver ../templates/subjects.example.json):
  {"subjects": [{"name": "Avion", "center": [x, y, z], "radius": r}, ...],
   "shots": ["hero", "turntable:8", "lineup", "closeups", {"name": "accion1", "loc": [..], "rot": [pitch, yaw, roll]}],
   "fov": 90, "aspect": 1.7778, "margin": 1.15}
  center y radius en cm: centro y media diagonal de la caja del actor (render_shots.py bounds los saca por MCP).
  fov: FOV horizontal de la cámara (el viewport del editor usa 90 por defecto).
Salida: lista de tomas {"name", "loc": [x, y, z], "rot": [pitch, yaw, roll]} en JSON.

Uso: python render_plan.py subjects.json [--out plan.json]
"""
import json
import math
import sys

HERO = (35.0, 20.0)  # azimut, elevación: 3/4 frontal un poco desde arriba, la toma "bonita"
TURN_EL = 15.0


def vfov_deg(hfov_deg, aspect):
    """FOV vertical a partir del horizontal y la relación de aspecto (ancho/alto)."""
    return math.degrees(2 * math.atan(math.tan(math.radians(hfov_deg) / 2) / aspect))


def fit_distance(radius, hfov_deg=90.0, aspect=16 / 9, margin=1.15):
    """Distancia para que una esfera de ese radio entre completa en cuadro, con margen."""
    if radius <= 0:
        raise ValueError("radius debe ser > 0")
    half = math.radians(min(hfov_deg, vfov_deg(hfov_deg, aspect)) / 2)
    return margin * radius / math.sin(half)


def look_pose(center, distance, az_deg, el_deg):
    """Cámara a `distance` de center en (azimut, elevación), mirando a center. rot = [pitch, yaw, roll]."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    cx, cy, cz = center
    loc = [cx + distance * math.cos(el) * math.cos(az),
           cy + distance * math.cos(el) * math.sin(az),
           cz + distance * math.sin(el)]
    return loc, [-float(el_deg), (az_deg + 180.0) % 360.0, 0.0]


def group_sphere(subjects):
    """Centro y radio de una esfera que contiene a todos los sujetos (lineup)."""
    if not subjects:
        raise ValueError("no hay sujetos")
    lo = [min(s["center"][i] - s["radius"] for s in subjects) for i in range(3)]
    hi = [max(s["center"][i] + s["radius"] for s in subjects) for i in range(3)]
    c = [(a + b) / 2 for a, b in zip(lo, hi)]
    r = max(math.dist(c, s["center"]) + s["radius"] for s in subjects)
    return c, r


def validate(cfg):
    errs = []
    subs = cfg.get("subjects") or []
    if not subs:
        errs.append("falta subjects")
    names = set()
    for s in subs:
        n = s.get("name", "")
        if not n or not all(ch.isalnum() or ch in "_-" for ch in n):
            errs.append("nombre invalido: %r (letras, numeros, _ o -)" % n)
        if n in names:
            errs.append("nombre repetido: " + n)
        names.add(n)
        if len(s.get("center", [])) != 3:
            errs.append("%s: center debe tener 3 numeros" % n)
        if not isinstance(s.get("radius"), (int, float)) or s["radius"] <= 0:
            errs.append("%s: radius debe ser > 0" % n)
    if not cfg.get("shots"):
        errs.append("falta shots")
    return errs


def build_plan(cfg):
    errs = validate(cfg)
    if errs:
        raise ValueError("; ".join(errs))
    fov, aspect = float(cfg.get("fov", 90)), float(cfg.get("aspect", 16 / 9))
    margin = float(cfg.get("margin", 1.15))
    subs = cfg["subjects"]
    main = subs[0]
    shots = []

    def add(name, center, radius, az, el):
        loc, rot = look_pose(center, fit_distance(radius, fov, aspect, margin), az, el)
        shots.append({"name": name, "loc": [round(v, 2) for v in loc], "rot": [round(v, 3) for v in rot]})

    for spec in cfg["shots"]:
        if isinstance(spec, dict):
            if not spec.get("name") or len(spec.get("loc", [])) != 3 or len(spec.get("rot", [])) < 2:
                raise ValueError("toma a mano necesita name, loc [x,y,z] y rot [pitch,yaw(,roll)]: %r" % spec)
            rot = list(spec["rot"]) + [0.0] * (3 - len(spec["rot"]))
            shots.append({"name": spec["name"], "loc": list(spec["loc"]), "rot": rot})
        elif spec == "hero":
            add("hero_" + main["name"], main["center"], main["radius"], *HERO)
        elif spec.startswith("turntable"):
            n = int(spec.split(":")[1]) if ":" in spec else 8
            if not 2 <= n <= 36:
                raise ValueError("turntable entre 2 y 36 angulos")
            for i in range(n):
                add("turn_%s_%02d" % (main["name"], i), main["center"], main["radius"], 360.0 * i / n, TURN_EL)
        elif spec == "lineup":
            c, r = group_sphere(subs)
            add("lineup", c, r, 0.0, 12.0)  # de frente y bajo: todos a la vista, como una foto de grupo
        elif spec == "closeups":
            for s in subs:
                add("close_" + s["name"], s["center"], s["radius"], *HERO)
        else:
            raise ValueError("toma desconocida: %r (hero, turntable:N, lineup, closeups o dict)" % spec)
    seen = set()
    for s in shots:
        if s["name"] in seen:
            raise ValueError("toma repetida: " + s["name"])
        seen.add(s["name"])
    return shots


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    with open(argv[1], encoding="utf-8") as f:
        cfg = json.load(f)
    try:
        plan = build_plan(cfg)
    except ValueError as e:
        print("PLAN_FAIL " + str(e))
        return 1
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    text = json.dumps(plan, indent=1)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)
    print("PLAN_OK %d tomas" % len(plan), file=sys.stderr if not out else sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
