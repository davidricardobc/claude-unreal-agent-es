#!/usr/bin/env python3
"""Valida manifiestos de loseta (JSON). Python puro, sin Unreal.

Uso:
  python validate_tile_manifest.py tile_a.json [tile_b.json ...]
  python validate_tile_manifest.py a.json b.json --adjacent a.json:E:b.json:W

Salida: una línea por problema (ERROR o WARN) y al final VALID o INVALID.
Código de salida 0 solo si no hay ERROR.
Los límites de rendimiento son propuestas a medir, no cifras oficiales.
"""
import json
import sys
import zlib

SIDES = ("N", "E", "S", "W")
CW = {"N": "E", "E": "S", "S": "W", "W": "N"}  # giro de 90 grados horario

DEFAULT_BUDGET = {  # por loseta, pensado para GPU de 6 GB con losetas residentes
    "triangles": 400000,
    "draw_calls": 600,
    "texture_mb": 96,
    "instances": 20000,
}
REQUIRED = ("tile_id", "size_cm", "grid_cm", "edges")


def rotate_edges(edges, quarter_turns):
    """Devuelve los bordes tras girar 90*quarter_turns grados horario."""
    out = dict(edges)
    for _ in range(quarter_turns % 4):
        out = {CW[s]: out[s] for s in SIDES}
    return out


def tile_seed(tile_id):
    """Semilla estable desde el ID (no usar hash(): Python lo aleatoriza por proceso)."""
    return zlib.crc32(str(tile_id).encode("utf-8")) & 0x7FFFFFFF


def edge_key(edge):
    return (edge.get("profile"), edge.get("height_cm"), edge.get("strip_cm"))


def validate_manifest(m, budget=None):
    """Devuelve lista de (nivel, mensaje). Nivel: ERROR o WARN."""
    budget = dict(DEFAULT_BUDGET, **(budget or {}))
    issues = []

    def err(t):
        issues.append(("ERROR", t))

    def warn(t):
        issues.append(("WARN", t))

    for k in REQUIRED:
        if k not in m:
            err("falta el campo '%s'" % k)
    if issues:
        return issues

    size, grid = m["size_cm"], m["grid_cm"]
    if (not isinstance(size, list) or len(size) != 2
            or not all(isinstance(v, (int, float)) and v > 0 for v in size)):
        err("size_cm debe ser [x, y] con numeros positivos")
        return issues
    if not isinstance(grid, (int, float)) or grid <= 0:
        err("grid_cm debe ser un numero positivo")
        return issues
    for axis, v in zip("xy", size):
        if v % grid:
            err("size_cm.%s=%s no es multiplo de grid_cm=%s" % (axis, v, grid))
    rotatable = m.get("rotatable", True)
    if size[0] != size[1]:
        if rotatable:
            err("loseta no cuadrada con rotatable=true: no gira 90/270 sin huecos")
        else:
            warn("loseta no cuadrada (rotatable=false)")

    edges = m["edges"]
    for s in SIDES:
        e = edges.get(s)
        if not isinstance(e, dict):
            err("falta el borde %s" % s)
            continue
        if not e.get("profile"):
            err("borde %s: falta 'profile'" % s)
        if not isinstance(e.get("height_cm"), (int, float)):
            err("borde %s: falta 'height_cm' numerico" % s)
        mid = size[0] if s in ("N", "S") else size[1]  # N/S corren sobre X
        if "road_center_cm" in e and e["road_center_cm"] != mid / 2:
            warn("borde %s: road_center_cm no esta en el punto medio (%s); "
                 "al girar o espejar no encaja" % (s, mid / 2))
    if not any(i[0] == "ERROR" for i in issues):
        keys = set(edge_key(edges[s]) for s in SIDES)
        if len(keys) > 1 and rotatable:
            err("rotatable=true exige los 4 bordes iguales (profile, height_cm, "
                "strip_cm): una copia girada 90 pondria bordes distintos juntos. "
                "Igualar los bordes o poner rotatable=false")

    half = (size[0] / 2, size[1] / 2)
    for i, p in enumerate(m.get("placements", [])):
        loc = p.get("location_cm")
        if not (isinstance(loc, list) and len(loc) == 3):
            err("placements[%d]: location_cm debe ser [x, y, z]" % i)
            continue
        if abs(loc[0]) > half[0] or abs(loc[1]) > half[1]:
            err("placements[%d] (%s) fuera de la loseta; el origen de la "
                "loseta es su centro" % (i, p.get("asset", "?")))
        snap = p.get("snap_cm", m.get("snap_cm"))
        if snap and (loc[0] % snap or loc[1] % snap):
            warn("placements[%d] no esta en la rejilla de %s cm" % (i, snap))
        a = str(p.get("asset", ""))
        if not (a.startswith("/Game/") or a.startswith("/Engine/BasicShapes/")):
            warn("placements[%d]: asset sin ruta /Game/" % i)
        sc = p.get("scale")
        if sc is not None and not (isinstance(sc, (int, float)) and sc > 0 or
                                   isinstance(sc, list) and len(sc) == 3 and all(isinstance(v, (int, float)) and v > 0 for v in sc)):
            err("placements[%d]: scale debe ser un numero o [x, y, z] positivos" % i)

    pcg = m.get("pcg")
    if pcg:
        if pcg.get("mode") != "baked":
            err("pcg.mode debe ser 'baked' (el PCG en runtime ignora el "
                "transform del Level Instance)")
        if "seed" not in pcg:
            err("pcg.seed falta (usar semilla por tile_id, no por posicion)")

    stats = m.get("stats", {})
    for k, limit in budget.items():
        v = stats.get(k)
        if v is None:
            warn("stats.%s sin medir" % k)
        elif v > limit:
            err("stats.%s=%s supera el presupuesto %s" % (k, v, limit))
    return issues


def check_adjacent_rotations(ma, side_a, mb, side_b):
    """Como check_adjacent, pero para todos los giros q de A y r de B.

    side_a/side_b son los lados FÍSICOS que se tocan tras girar. Solo se exige
    encaje en los giros permitidos (rotatable=false permite solo 0).
    """
    issues = []
    qs = range(4) if ma.get("rotatable", True) else (0,)
    rs = range(4) if mb.get("rotatable", True) else (0,)
    for q in qs:
        for r in rs:
            a = dict(ma, edges=rotate_edges(ma["edges"], q))
            b = dict(mb, edges=rotate_edges(mb["edges"], r))
            for lvl, msg in check_adjacent(a, side_a, b, side_b):
                issues.append((lvl, "giros A=%d B=%d: %s" % (q * 90, r * 90, msg)))
    return issues


def check_adjacent(ma, side_a, mb, side_b):
    """El borde side_a de A toca el borde side_b de B: deben coincidir."""
    ea, eb = ma["edges"][side_a], mb["edges"][side_b]
    if edge_key(ea) != edge_key(eb):
        return [("ERROR", "%s.%s != %s.%s: %s vs %s" % (
            ma["tile_id"], side_a, mb["tile_id"], side_b,
            edge_key(ea), edge_key(eb)))]
    return []


def main(argv):
    adj = []
    if "--adjacent" in argv:
        i = argv.index("--adjacent")
        adj = argv[i + 1:]
        argv = argv[:i]
    files = argv
    if not files:
        print(__doc__)
        return 2
    mans, bad = {}, False
    for f in files:
        with open(f, encoding="utf-8") as fh:
            m = json.load(fh)
        mans[f] = m
        for lvl, msg in validate_manifest(m):
            print("%s %s: %s" % (lvl, f, msg))
            bad = bad or lvl == "ERROR"
    for spec in adj:
        fa, sa, fb, sb = spec.split(":")
        for lvl, msg in check_adjacent_rotations(mans[fa], sa, mans[fb], sb):
            print("%s %s: %s" % (lvl, spec, msg))
            bad = bad or lvl == "ERROR"
    print("INVALID" if bad else "VALID")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
