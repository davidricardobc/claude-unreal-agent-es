"""Sesión de pruebas de vuelo: avanza maniobras tick a tick, guarda un CSV por maniobra y decide el resultado.
Puro Python 3 (sin Unreal): el runner le pasa un adaptador de pawn. Se prueba con un pawn falso.

Adaptador de pawn (lo implementa ue_flight_runner.py):
  reset(setup)                       coloca el pawn; lanza PawnError si no puede cumplir el setup
  set_stick(throttle, pitch, roll, yaw)
  sample() -> (loc(x,y,z), rot(pitch,roll,yaw), vel(x,y,z))
Reglas de honestidad:
  - Al empezar se borra <id>.csv de corridas viejas y se escribe run.json {status: running, started}.
  - Al terminar se analiza cada CSV con sus criterios y run.json queda en pass o fail.
  - success = todas las maniobras corrieron Y pasaron. Cualquier otra cosa es falla (incluye tiempo agotado).
"""
import json
import os
import time

import analyze_flight as af
from maneuver_script import stick_at

CSV_HEADER = ",".join(af.FIELDS)


class PawnError(Exception):
    pass


def sample_row(t, loc, rot, vel):
    """Una fila CSV: t,x,y,z,pitch,roll,yaw,vx,vy,vz. rot = (pitch, roll, yaw)."""
    vals = (t,) + tuple(loc) + tuple(rot) + tuple(vel)
    return ",".join(repr(float(v)) for v in vals)


class Session:
    def __init__(self, maneuvers, out_dir, unit_scale=0.01, max_wall_s=900.0, clock=time.time):
        self.maneuvers = maneuvers
        self.out_dir = out_dir
        self.unit_scale = unit_scale
        self.max_wall_s = max_wall_s
        self.clock = clock
        self.i = 0
        self.t = 0.0
        self.rows = []
        self.state = "idle"  # idle, running, done, fail
        self.reason = ""
        self.started = 0.0
        self.report = []
        self.passed = False
        self._needs_reset = True

    # --- archivos ---
    def _run_json(self, status):
        with open(os.path.join(self.out_dir, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"status": status, "started": self.started, "reason": self.reason,
                       "maneuvers": [m["id"] for m in self.maneuvers]}, f)

    def start(self):
        os.makedirs(self.out_dir, exist_ok=True)
        self.started = self.clock()
        for m in self.maneuvers:
            p = os.path.join(self.out_dir, m["id"] + ".csv")
            if os.path.exists(p):
                os.remove(p)
        self._run_json("running")
        self.state = "running"

    def fail(self, reason):
        self.state, self.reason, self.passed = "fail", reason, False
        self._run_json("fail")

    # --- avance ---
    def tick(self, delta, pawn):
        """Avanza un tick. Devuelve el estado: running, done o fail."""
        if self.state != "running":
            return self.state
        if self.clock() - self.started > self.max_wall_s:
            self.fail("tiempo agotado (%.0f s) en la maniobra %s" % (self.max_wall_s, self.maneuvers[self.i]["id"]))
            return self.state
        m = self.maneuvers[self.i]
        try:
            if self._needs_reset:
                pawn.reset(m.get("setup", {}))
                self._needs_reset = False
            s = stick_at(m, self.t)
            pawn.set_stick(s["throttle"], s["pitch"], s["roll"], s["yaw"])
            loc, rot, vel = pawn.sample()
        except PawnError as e:
            self.fail("%s: %s" % (m["id"], e))
            return self.state
        self.rows.append(sample_row(self.t, loc, rot, vel))
        self.t += delta
        if self.t >= m["duration_s"]:
            self._finish_maneuver(m)
        return self.state

    def _finish_maneuver(self, m):
        path = os.path.join(self.out_dir, m["id"] + ".csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(CSV_HEADER + "\n" + "\n".join(self.rows) + "\n")
        self.i += 1
        self.t = 0.0
        self.rows = []
        self._needs_reset = True
        if self.i >= len(self.maneuvers):
            self._conclude()

    def _conclude(self):
        failed = 0
        for m in self.maneuvers:
            res = af.analyze_file(os.path.join(self.out_dir, m["id"] + ".csv"), m.get("criteria", {}), self.unit_scale)
            bad = [r for r in res if not r[3]]
            failed += bool(bad)
            self.report.append("%s %s" % ("PASS" if not bad else "FAIL", m["id"]))
            for n, v, lim, ok in bad:
                self.report.append("  MAL %s = %s (limite %s)" % (n, v, json.dumps(lim)))
        self.passed = failed == 0
        if self.passed:
            self.state = "done"
            self._run_json("pass")
        else:
            self.fail("%d maniobra(s) no cumplen criterios" % failed)

    def final_line(self):
        """KIT_OK solo si todas las maniobras corrieron y pasaron."""
        if self.state == "done" and self.passed:
            return "KIT_OK"
        return "KIT_FAIL " + (self.reason or "la sesión no terminó")
