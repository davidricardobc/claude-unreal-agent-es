"""Analiza CSV de trayectoria y compara con criterios. Puro Python 3, sin Unreal.

CSV (una fila por muestra): t,x,y,z,pitch,roll,yaw,vx,vy,vz
Unidades de Unreal (cm y grados); --unit-scale 0.01 pasa cm a m (por defecto).
Uso:
  python analyze_flight.py --maneuvers maneuvers.example.json --dir Saved/FlightTests
  python analyze_flight.py --csv turn360.csv --criteria '{"turn360_time_s":{"max":14}}'
Salida: tabla pasa/falla; última línea FLIGHT_PASS o FLIGHT_FAIL. Código de salida 0 pasa, 1 falla.
Criterios: {"metrica": {"min": a, "max": b}}. Una métrica que no se pudo calcular (None) falla.
Con --maneuvers, si hay run.json en la carpeta, un CSV anterior a la corrida falla.
Para booleanos: {"has_nan": {"equals": false}}.
Especial: "recover_speed_mps": 40 calcula stall_recovery_time_s (desde la velocidad mínima hasta ese valor).
"""
import argparse
import csv
import json
import math
import os
import sys

FIELDS = ("t", "x", "y", "z", "pitch", "roll", "yaw", "vx", "vy", "vz")


def load_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            row = {}
            for k in FIELDS:
                try:
                    row[k] = float(r.get(k, "nan"))
                except (TypeError, ValueError):
                    row[k] = float("nan")
            rows.append(row)
    return rows


def unwrap_deg(angles):
    out, off = [], 0.0
    for i, a in enumerate(angles):
        if i and math.isfinite(a) and math.isfinite(angles[i - 1]):
            d = a - angles[i - 1]
            if d > 180:
                off -= 360
            elif d < -180:
                off += 360
        out.append(a + off)
    return out


def time_to_turn(ts, angles, target_deg):
    """Primer t (desde el inicio) en que el cambio acumulado de ángulo llega a target_deg. None si nunca."""
    u = unwrap_deg(angles)
    for t, a in zip(ts, u):
        if math.isfinite(a) and abs(a - u[0]) >= target_deg:
            return t - ts[0]
    return None


def path_angle_deg(rows):
    """Ángulo de la trayectoria en el plano vertical del rumbo inicial. Crece en un loop sin saltos de Euler."""
    h = None
    for r in rows:
        n = math.hypot(r["vx"], r["vy"])
        if n > 1e-6:
            h = (r["vx"] / n, r["vy"] / n)
            break
    if h is None:
        return [float("nan")] * len(rows)
    return [math.degrees(math.atan2(r["vz"], r["vx"] * h[0] + r["vy"] * h[1])) for r in rows]


def rate_rms(ts, angles, last_s):
    """RMS de la tasa angular (grados/s) en los últimos last_s segundos."""
    u = unwrap_deg(angles)
    t_end = ts[-1]
    sq, n = 0.0, 0
    for i in range(1, len(ts)):
        if ts[i] >= t_end - last_s and ts[i] > ts[i - 1]:
            r = (u[i] - u[i - 1]) / (ts[i] - ts[i - 1])
            sq += r * r
            n += 1
    return math.sqrt(sq / n) if n else None


def compute_metrics(rows, unit_scale=0.01, settle_window_s=2.0):
    """unit_scale convierte las unidades del CSV a metros. Devuelve dict de métricas (None si no aplica)."""
    if len(rows) < 3:
        return {"samples": len(rows)}
    m = {}
    ts = [r["t"] for r in rows]
    m["samples"] = len(rows)
    m["has_nan"] = any(not math.isfinite(r[k]) for r in rows for k in FIELDS)
    if m["has_nan"]:
        return m  # el resto no es fiable con NaN
    m["duration_s"] = ts[-1] - ts[0]
    m["time_monotonic"] = all(b > a for a, b in zip(ts, ts[1:]))
    z = [r["z"] * unit_scale for r in rows]
    m["altitude_lost_m"] = max(0.0, z[0] - min(z))
    m["altitude_gained_m"] = max(0.0, max(z) - z[0])
    m["final_altitude_delta_m"] = z[-1] - z[0]
    sp = [math.sqrt(r["vx"] ** 2 + r["vy"] ** 2 + r["vz"] ** 2) * unit_scale for r in rows]
    m["min_speed_mps"] = min(sp)
    m["max_speed_mps"] = max(sp)
    jump = 0.0
    for a, b in zip(rows, rows[1:]):
        d = math.sqrt((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2 + (b["z"] - a["z"]) ** 2) * unit_scale
        jump = max(jump, d)
    m["max_step_jump_m"] = jump
    m["turn360_time_s"] = time_to_turn(ts, [r["yaw"] for r in rows], 360.0)
    m["turn180_time_s"] = time_to_turn(ts, [r["yaw"] for r in rows], 180.0)
    m["loop_time_s"] = time_to_turn(ts, path_angle_deg(rows), 360.0)
    m["settled_pitch_rate_rms"] = rate_rms(ts, [r["pitch"] for r in rows], settle_window_s)
    m["settled_roll_rate_rms"] = rate_rms(ts, [r["roll"] for r in rows], settle_window_s)
    m["settled_yaw_rate_rms"] = rate_rms(ts, [r["yaw"] for r in rows], settle_window_s)
    m["max_abs_pitch"] = max(abs(r["pitch"]) for r in rows)
    m["_speeds"] = sp
    m["_ts"] = [t - ts[0] for t in ts]
    return m


def recovery_time(metrics, recover_speed_mps):
    """Segundos desde la velocidad mínima hasta alcanzar recover_speed_mps. None si nunca."""
    sp, ts = metrics.get("_speeds"), metrics.get("_ts")
    if not sp:
        return None
    i_min = sp.index(min(sp))
    for i in range(i_min, len(sp)):
        if sp[i] >= recover_speed_mps:
            return ts[i] - ts[i_min]
    return None


def check(metrics, criteria):
    """Devuelve lista de (nombre, valor, límite, ok)."""
    crit = dict(criteria)
    p = crit.pop("recover_speed_mps", None)
    if p is not None:
        metrics["stall_recovery_time_s"] = recovery_time(metrics, p)
    out = []
    for name, lim in crit.items():
        v = metrics.get(name)
        ok = v is not None
        if ok and isinstance(v, bool):
            ok = v == lim.get("equals", False)
        elif ok:
            if "min" in lim and v < lim["min"]:
                ok = False
            if "max" in lim and v > lim["max"]:
                ok = False
        out.append((name, v, lim, ok))
    return out


DEFAULT_CRITERIA = {"has_nan": {"equals": False}, "time_monotonic": {"equals": True}}


def analyze_file(path, criteria, unit_scale=0.01):
    m = compute_metrics(load_csv(path), unit_scale)
    merged = {**DEFAULT_CRITERIA, **criteria}
    if m["samples"] < 3:
        # muestras insuficientes: no es NaN; el resto de métricas no existe
        merged = {"samples": {"min": 3}}
    elif m.get("has_nan"):
        # con NaN solo se reporta eso; el resto de métricas no existe
        merged = {"has_nan": {"equals": False}}
    return check(m, merged)


def check_fresh(directory, csv_path):
    """None si el CSV es de la corrida registrada en run.json (o no hay run.json); si no, el motivo de falla.
    run.json lo escribe el runner al empezar: {status, started}. Un CSV más viejo es de otra corrida."""
    rj = os.path.join(directory, "run.json")
    if not os.path.exists(rj):
        return None
    with open(rj, encoding="utf-8") as f:
        run = json.load(f)
    if run.get("status") == "running":
        return "la corrida registrada en run.json no terminó"
    if os.path.getmtime(csv_path) < run.get("started", 0) - 1.0:
        return "el CSV es anterior a la corrida (de una corrida vieja)"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--maneuvers", help="JSON con maniobras y criterios")
    ap.add_argument("--dir", default=".", help="carpeta con <id>.csv por maniobra")
    ap.add_argument("--csv", help="un solo CSV")
    ap.add_argument("--criteria", help="JSON inline de criterios (con --csv)")
    ap.add_argument("--unit-scale", type=float, default=0.01, help="unidades del CSV a metros (cm=0.01)")
    a = ap.parse_args(argv)
    jobs = []
    if a.csv:
        jobs.append((os.path.basename(a.csv), a.csv, json.loads(a.criteria or "{}")))
    elif a.maneuvers:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from maneuver_script import load_maneuvers
        for mv in load_maneuvers(a.maneuvers):
            jobs.append((mv["id"], os.path.join(a.dir, mv["id"] + ".csv"), mv.get("criteria", {})))
    else:
        ap.error("usa --csv o --maneuvers")
    failed = 0
    for name, path, crit in jobs:
        if not os.path.exists(path):
            print("FAIL %s: falta %s" % (name, path))
            failed += 1
            continue
        stale = check_fresh(os.path.dirname(path) or ".", path)
        if stale:
            print("FAIL %s: %s" % (name, stale))
            failed += 1
            continue
        res = analyze_file(path, crit, a.unit_scale)
        bad = [r for r in res if not r[3]]
        print("%s %s" % ("PASS" if not bad else "FAIL", name))
        for n, v, lim, ok in res:
            vs = "None" if v is None else (str(v) if isinstance(v, bool) else "%.3f" % v)
            print("  %s %s = %s  (limite %s)" % ("ok  " if ok else "MAL ", n, vs, json.dumps(lim)))
        failed += bool(bad)
    print("FLIGHT_PASS" if not failed else "FLIGHT_FAIL (%d)" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
