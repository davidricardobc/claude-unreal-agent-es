"""Ajuste de PID para bots contra una planta simulada. Puro Python 3, sin Unreal.

Dos métodos:
  1. Ziegler-Nichols simplificado: sube Kp (solo P) hasta oscilación sostenida -> Ku y Pu -> tabla.
  2. Barrido de ganancias (rejilla) o twiddle (descenso por coordenadas) con métrica de error.
La "planta" es un modelo de primer orden con retardo (y opcionalmente integrador, como alabeo = integral de la tasa).
Para planta real: medir la respuesta al escalón del pawn, ajustar K, tau, delay, y afinar contra el modelo.
Métrica de costo: IAE (error absoluto integrado) + penalización por sobrepaso mayor al límite.

Uso:
  python pid_tune.py --K 1 --tau 0.4 --delay 0.1 --integrating --method zn
  python pid_tune.py --K 1 --tau 0.4 --delay 0.1 --method twiddle
Última línea: PID_TUNE_OK.
"""
import argparse
import itertools
import json
import math
import sys


class Plant:
    """y' = (K*u(t-delay) - x)/tau ; salida = x, o integral de x si integrating."""

    def __init__(self, K=1.0, tau=0.5, delay=0.0, integrating=False, dt=0.01):
        self.K, self.tau, self.delay, self.integrating, self.dt = K, tau, delay, integrating, dt
        self.reset()

    def reset(self):
        self.x = 0.0
        self.y = 0.0
        self.buf = [0.0] * int(round(self.delay / self.dt))

    def step(self, u):
        self.buf.append(u)
        ud = self.buf.pop(0)
        self.x += self.dt * (self.K * ud - self.x) / self.tau
        if self.integrating:
            self.y += self.dt * self.x
        else:
            self.y = self.x
        return self.y


class PID:
    """PID con derivada sobre la medición, anti-windup por límite de integral y salida saturada."""

    def __init__(self, kp, ki=0.0, kd=0.0, out_limit=1.0, dt=0.01):
        self.kp, self.ki, self.kd, self.lim, self.dt = kp, ki, kd, out_limit, dt
        self.i = 0.0
        self.prev = None

    def update(self, setpoint, meas):
        e = setpoint - meas
        d = 0.0 if self.prev is None else -(meas - self.prev) / self.dt
        self.prev = meas
        self.i += e * self.dt
        if self.ki:
            self.i = max(-self.lim / self.ki, min(self.lim / self.ki, self.i))
        u = self.kp * e + self.ki * self.i + self.kd * d
        return max(-self.lim, min(self.lim, u))


def simulate_step(plant, kp, ki=0.0, kd=0.0, T=10.0, setpoint=1.0, out_limit=1e9):
    """Devuelve (ts, ys, us). out_limit alto por defecto para el análisis lineal."""
    plant.reset()
    pid = PID(kp, ki, kd, out_limit, plant.dt)
    ts, ys, us = [], [], []
    y = 0.0
    for n in range(int(T / plant.dt)):
        u = pid.update(setpoint, y)
        y = plant.step(u)
        ts.append(n * plant.dt)
        ys.append(y)
        us.append(u)
        if not math.isfinite(y) or abs(y) > 1e6:
            break
    return ts, ys, us


def step_metrics(ts, ys, setpoint=1.0, band=0.02):
    """overshoot_pct, settling_time_s (None si no asienta), iae, steady_error, diverged."""
    if not ys or not all(math.isfinite(y) for y in ys) or max(abs(y) for y in ys) > 1e5:
        return {"diverged": True, "overshoot_pct": float("inf"), "settling_time_s": None,
                "iae": float("inf"), "steady_error": float("inf")}
    dt = ts[1] - ts[0]
    iae = sum(abs(setpoint - y) for y in ys) * dt
    over = max(0.0, (max(ys) - setpoint) / abs(setpoint)) * 100.0
    settle = None
    for i in range(len(ys) - 1, -1, -1):
        if abs(ys[i] - setpoint) > band * abs(setpoint):
            settle = ts[min(i + 1, len(ts) - 1)] if i < len(ys) - 1 else None
            break
    else:
        settle = 0.0
    tail = ys[-max(1, len(ys) // 20):]
    return {"diverged": False, "overshoot_pct": over, "settling_time_s": settle,
            "iae": iae, "steady_error": abs(setpoint - sum(tail) / len(tail))}


def _peaks(ys, start):
    return [ys[i] for i in range(max(start, 1), len(ys) - 1) if ys[i] > ys[i - 1] and ys[i] >= ys[i + 1]]


def ultimate_gain(plant, kp_max=200.0, T=40.0, iters=30):
    """Bisección de Kp (solo P) hasta el borde de oscilación sostenida. Devuelve (Ku, Pu) o None.
    Solo existe si la planta tiene retardo o integrador con lag suficiente."""
    def grows(kp):
        ts, ys, _ = simulate_step(plant, kp, T=T)
        if not all(math.isfinite(y) for y in ys) or max(abs(y) for y in ys) > 1e3:
            return True
        pk = _peaks([abs(y - 1.0) for y in ys], len(ys) // 3)
        return len(pk) >= 2 and pk[-1] >= 0.98 * pk[-2]

    lo, hi = 0.01, kp_max
    if not grows(hi):
        return None
    if grows(lo):
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if grows(mid) else (mid, hi)
    ku = hi
    ts, ys, _ = simulate_step(plant, ku, T=T)
    err = [y - 1.0 for y in ys]
    idx = [i for i in range(len(err) // 2, len(err) - 1) if err[i] > 0 >= err[i + 1]]
    if len(idx) < 2:
        return None
    pu = (ts[idx[-1]] - ts[idx[0]]) / (len(idx) - 1)
    return ku, pu


ZN_RULES = {  # nombre: (kp/Ku, Ti/Pu, Td/Pu)
    "classic": (0.60, 0.50, 0.125),
    "some_overshoot": (0.33, 0.50, 0.333),
    "no_overshoot": (0.20, 0.50, 0.333),
    "pi": (0.45, 1 / 1.2, 0.0),
    "p": (0.50, None, 0.0),
}


def zn_gains(ku, pu, rule="classic"):
    a, ti, td = ZN_RULES[rule]
    kp = a * ku
    return {"kp": kp, "ki": 0.0 if ti is None else kp / (ti * pu), "kd": kp * td * pu}


def cost(plant, gains, T=10.0, overshoot_limit=15.0):
    ts, ys, _ = simulate_step(plant, gains["kp"], gains["ki"], gains["kd"], T=T)
    m = step_metrics(ts, ys)
    if m["diverged"]:
        return 1e9, m
    pen = max(0.0, m["overshoot_pct"] - overshoot_limit) * 0.05
    return m["iae"] + pen + (0.0 if m["settling_time_s"] is not None else 5.0), m


def gain_sweep(plant, kps, kis, kds, T=10.0, overshoot_limit=15.0):
    """Rejilla completa. Devuelve lista ordenada por costo [(costo, gains, métricas)]."""
    rows = []
    for kp, ki, kd in itertools.product(kps, kis, kds):
        g = {"kp": kp, "ki": ki, "kd": kd}
        c, m = cost(plant, g, T, overshoot_limit)
        rows.append((c, g, m))
    rows.sort(key=lambda r: r[0])
    return rows


def twiddle(plant, start, tol=1e-3, T=10.0, overshoot_limit=15.0, max_iter=200):
    """Descenso por coordenadas. Una ganancia por vez; deja de mejorar cuando los pasos bajan de tol."""
    p = [start["kp"], start["ki"], start["kd"]]
    dp = [max(abs(v) * 0.3, 0.05) for v in p]
    names = ("kp", "ki", "kd")

    def c_of(v):
        g = dict(zip(names, (max(0.0, x) for x in v)))
        return cost(plant, g, T, overshoot_limit)[0]

    best = c_of(p)
    for _ in range(max_iter):
        if sum(dp) < tol:
            break
        for i in range(3):
            p[i] += dp[i]
            c = c_of(p)
            if c < best:
                best, dp[i] = c, dp[i] * 1.1
                continue
            p[i] -= 2 * dp[i]
            c = c_of(p)
            if c < best:
                best, dp[i] = c, dp[i] * 1.1
            else:
                p[i] += dp[i]
                dp[i] *= 0.9
    g = dict(zip(names, (max(0.0, x) for x in p)))
    return g, best


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--K", type=float, default=1.0)
    ap.add_argument("--tau", type=float, default=0.4)
    ap.add_argument("--delay", type=float, default=0.1)
    ap.add_argument("--integrating", action="store_true")
    ap.add_argument("--dt", type=float, default=0.01)
    ap.add_argument("--method", choices=("zn", "sweep", "twiddle"), default="zn")
    ap.add_argument("--rule", choices=sorted(ZN_RULES), default="some_overshoot")
    a = ap.parse_args(argv)
    plant = Plant(a.K, a.tau, a.delay, a.integrating, a.dt)
    out = {"plant": {"K": a.K, "tau": a.tau, "delay": a.delay, "integrating": a.integrating}}
    if a.method == "zn":
        r = ultimate_gain(plant)
        if r is None:
            print("Sin ganancia ultima: la planta no oscila (falta retardo o integrador). Usa --method sweep.")
            return 1
        ku, pu = r
        g = zn_gains(ku, pu, a.rule)
        out.update({"Ku": ku, "Pu": pu, "rule": a.rule, "gains": g, "metrics": cost(plant, g)[1]})
    elif a.method == "sweep":
        k = 1.0 / max(a.K, 1e-9)  # la rejilla se escala por 1/K: el lazo abierto tiene ganancia K
        rows = gain_sweep(plant, [x * k for x in (0.5, 1, 2, 4, 8)], [x * k for x in (0, 0.5, 1, 2)], [x * k for x in (0, 0.05, 0.1, 0.2)])
        out.update({"gains": rows[0][1], "metrics": rows[0][2], "cost": rows[0][0]})
    else:
        g, c = twiddle(plant, {"kp": 1.0, "ki": 0.1, "kd": 0.05})
        out.update({"gains": g, "cost": c, "metrics": cost(plant, g)[1]})
    print(json.dumps(out, indent=2))
    print("PID_TUNE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
