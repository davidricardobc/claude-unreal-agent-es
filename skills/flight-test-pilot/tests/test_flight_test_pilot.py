"""Pruebas puras (sin Unreal). Correr: python -m unittest discover -s .claude/skills/flight-test-pilot/tests"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import analyze_flight as af  # noqa: E402
import maneuver_script as ms  # noqa: E402
import pid_tune as pt  # noqa: E402
import ue_flight_runner as ur  # noqa: E402
import flight_session as fs  # noqa: E402
import json, tempfile, time  # noqa: E402,E401


def synth_turn(rate_dps=30.0, dur=20.0, hz=60.0):
    """Giro plano a velocidad 50 m/s (5000 cm/s), yaw crece y se envuelve a [-180,180]."""
    rows, n = [], int(dur * hz)
    for i in range(n):
        t = i / hz
        yaw = ((rate_dps * t + 180) % 360) - 180
        a = math.radians(rate_dps * t)
        rows.append({"t": t, "x": 0, "y": 0, "z": 100000.0, "pitch": 0, "roll": 45, "yaw": yaw,
                     "vx": 5000 * math.cos(a), "vy": 5000 * math.sin(a), "vz": 0})
    return rows


def synth_loop(rate_dps=60.0, dur=8.0, hz=60.0):
    rows, n = [], int(dur * hz)
    for i in range(n):
        t = i / hz
        a = math.radians(rate_dps * t)
        rows.append({"t": t, "x": 0, "y": 0, "z": 100000.0 + 1000 * (1 - math.cos(a)), "pitch": rate_dps * t % 360 - 180,
                     "roll": 0, "yaw": 0, "vx": 5000 * math.cos(a), "vy": 0, "vz": 5000 * math.sin(a)})
    return rows


class AnalyzeTests(unittest.TestCase):
    def test_turn360_time(self):
        m = af.compute_metrics(synth_turn(30.0))
        self.assertAlmostEqual(m["turn360_time_s"], 12.0, delta=0.05)
        self.assertAlmostEqual(m["turn180_time_s"], 6.0, delta=0.05)
        self.assertFalse(m["has_nan"])

    def test_turn_never_completes(self):
        m = af.compute_metrics(synth_turn(10.0, dur=20.0))  # 200 grados en 20 s
        self.assertIsNone(m["turn360_time_s"])
        res = af.check(m, {"turn360_time_s": {"max": 30}})
        self.assertFalse(res[0][3])

    def test_loop_time(self):
        m = af.compute_metrics(synth_loop(60.0, dur=8.0))
        self.assertAlmostEqual(m["loop_time_s"], 6.0, delta=0.05)

    def test_nan_fails(self):
        rows = synth_turn()
        rows[100]["z"] = float("nan")
        m = af.compute_metrics(rows)
        self.assertTrue(m["has_nan"])
        res = af.check(m, af.DEFAULT_CRITERIA)
        self.assertFalse(res[0][3])

    def test_altitude_lost_and_limits(self):
        rows = synth_turn()
        for i, r in enumerate(rows):
            r["z"] -= 20 * i  # baja 0,2 m por muestra
        m = af.compute_metrics(rows)
        self.assertAlmostEqual(m["altitude_lost_m"], 20 * (len(rows) - 1) * 0.01, places=3)
        ok = af.check(m, {"altitude_lost_m": {"max": 1000}})[0][3]
        bad = af.check(m, {"altitude_lost_m": {"max": 10}})[0][3]
        self.assertTrue(ok)
        self.assertFalse(bad)

    def test_stall_recovery(self):
        rows = []
        for i in range(600):
            t = i / 60.0
            v = 30 - 10 * t if t < 3 else (t - 3) * 10  # cae a 0 en t=3 y sube 10 m/s por s
            rows.append({"t": t, "x": 0, "y": 0, "z": 1e5, "pitch": 0, "roll": 0, "yaw": 0,
                         "vx": v * 100, "vy": 0, "vz": 0})
        m = af.compute_metrics(rows)
        res = af.check(m, {"recover_speed_mps": 25})
        self.assertEqual(res, [])  # sin otros criterios: solo calcula la métrica
        self.assertAlmostEqual(m["stall_recovery_time_s"], 2.5, delta=0.05)

    def test_teleport_detected(self):
        rows = synth_turn()
        for r in rows[200:]:
            r["x"] += 50000.0  # salto de 500 m
        m = af.compute_metrics(rows)
        self.assertGreater(m["max_step_jump_m"], 400)

    def test_csv_roundtrip(self):
        import tempfile
        rows = synth_turn(30.0, dur=14.0)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "turn360.csv")
            with open(p, "w", newline="") as f:
                f.write(",".join(af.FIELDS) + "\n")
                for r in rows:
                    f.write(",".join(repr(r[k]) for k in af.FIELDS) + "\n")
            res = af.analyze_file(p, {"turn360_time_s": {"max": 14}})
            self.assertTrue(all(r[3] for r in res))
            self.assertEqual(af.main(["--csv", p, "--criteria", '{"turn360_time_s":{"max":5}}']), 1)
            self.assertEqual(af.main(["--csv", p, "--criteria", '{"turn360_time_s":{"max":14}}']), 0)


class ManeuverTests(unittest.TestCase):
    M = {"id": "t", "steps": [{"t0": 0, "t1": 2, "stick": {"throttle": 1.0}},
                              {"t0": 2, "t1": 4, "stick": {"throttle": 1.0, "roll": 0.8}}]}

    def test_stick_at(self):
        self.assertEqual(ms.stick_at(self.M, 1.0)["roll"], 0.0)
        self.assertEqual(ms.stick_at(self.M, 3.0)["roll"], 0.8)
        after = ms.stick_at(self.M, 10.0)
        self.assertEqual(after["roll"], 0.0)
        self.assertEqual(after["throttle"], 1.0)

    def test_validate(self):
        self.assertEqual(ms.validate(self.M), [])
        bad = {"id": "x", "steps": [{"t0": 3, "t1": 1, "stick": {"roll": 2.0, "foo": 1}}]}
        self.assertEqual(len(ms.validate(bad)), 3)

    def test_example_json_loads(self):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "maneuvers.example.json")
        for m in ms.load_maneuvers(p):
            self.assertEqual(ms.validate(m), [], m["id"])


class RunnerTests(unittest.TestCase):
    def test_sample_row_matches_header(self):
        row = ur.sample_row(0.5, (1, 2, 3), (4, 5, 6), (7, 8, 9))
        self.assertEqual(len(row.split(",")), len(ur.CSV_HEADER.split(",")))


class FakePawn:
    """Pawn falso: avanza como un giro plano a 40 m/s con tasa de yaw proporcional al roll."""

    def __init__(self, can_speed=True, rate=30.0):
        self.can_speed, self.rate = can_speed, rate
        self.yaw = 0.0
        self.roll = 0.0
        self.z = 30000.0

    def reset(self, setup):
        if setup.get("speed_mps", 0) > 0 and not self.can_speed:
            raise fs.PawnError("sin SetInitialSpeed")
        self.yaw = 0.0
        self.z = setup.get("altitude_m", 0) * 100.0

    def set_stick(self, th, pi, ro, ya):
        self.roll = ro
        self.dyaw = self.rate * (1 if ro > 0.5 else 0)

    def sample(self):
        self.yaw += self.dyaw / 60.0
        a = math.radians(self.yaw)
        w = ((self.yaw + 180) % 360) - 180
        return (0, 0, self.z), (0, 45, w), (4000 * math.cos(a), 4000 * math.sin(a), 0)


class SessionTests(unittest.TestCase):
    MAN = [{"id": "turn", "duration_s": 14.0, "setup": {"altitude_m": 300, "speed_mps": 40},
            "steps": [{"t0": 0, "t1": 14, "stick": {"throttle": 1, "roll": 0.7}}],
            "criteria": {"turn360_time_s": {"max": 13}}}]

    def run_session(self, pawn, man=None, clock=time.time, max_wall=900):
        d = tempfile.mkdtemp()
        ses = fs.Session(man or self.MAN, d, max_wall_s=max_wall, clock=clock)
        ses.start()
        for _ in range(5000):
            if ses.tick(1 / 60.0, pawn) != "running":
                break
        return ses, d

    def test_kit_ok_only_after_run_and_pass(self):
        ses, d = self.run_session(FakePawn())
        self.assertEqual(ses.final_line(), "KIT_OK")
        self.assertTrue(os.path.exists(os.path.join(d, "turn.csv")))
        self.assertEqual(json.load(open(os.path.join(d, "run.json")))["status"], "pass")

    def test_no_kit_ok_before_running(self):
        d = tempfile.mkdtemp()
        ses = fs.Session(self.MAN, d)
        ses.start()
        self.assertNotEqual(ses.final_line(), "KIT_OK")  # recién pedido: nada corrió
        self.assertTrue(ses.final_line().startswith("KIT_FAIL"))

    def test_criteria_failure_is_fail(self):
        ses, _ = self.run_session(FakePawn(rate=10.0))
        self.assertTrue(ses.final_line().startswith("KIT_FAIL"))
        self.assertTrue(any(l.startswith("FAIL") for l in ses.report))

    def test_missing_initial_speed_fails_with_reason(self):
        ses, _ = self.run_session(FakePawn(can_speed=False))
        self.assertIn("SetInitialSpeed", ses.final_line())

    def test_timeout_is_fail(self):
        t = [0.0]

        def clock():
            t[0] += 100.0
            return t[0]
        ses, _ = self.run_session(FakePawn(), clock=clock, max_wall=250)
        self.assertIn("tiempo agotado", ses.final_line())

    def test_start_deletes_old_csv_and_stale_detected(self):
        d = tempfile.mkdtemp()
        old = os.path.join(d, "turn.csv")
        open(old, "w").write("t\n")
        os.utime(old, (1000, 1000))
        ses = fs.Session(self.MAN, d)
        ses.start()
        self.assertFalse(os.path.exists(old))
        ses.fail("x")  # cierra la corrida: status fail, ya no "running"
        # CSV viejo recreado a mano con mtime anterior a la corrida: se detecta
        open(old, "w").write("t\n")
        os.utime(old, (1000, 1000))
        self.assertIn("anterior", af.check_fresh(d, old))
        os.utime(old, None)
        self.assertIsNone(af.check_fresh(d, old))  # CSV nuevo de la corrida: pasa

    def test_run_json_running_blocks_analysis(self):
        d = tempfile.mkdtemp()
        fs.Session(self.MAN, d).start()
        p = os.path.join(d, "turn.csv")
        open(p, "w").write("x")
        self.assertIn("no terminó", af.check_fresh(d, p))

    def test_few_samples_message(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "a.csv")
        open(p, "w").write(",".join(af.FIELDS) + "\n0,0,0,0,0,0,0,0,0,0\n")
        res = af.analyze_file(p, {})
        self.assertEqual(res[0][0], "samples")
        self.assertFalse(res[0][3])
        self.assertNotIn("has_nan", [r[0] for r in res])

    def test_sweep_scales_with_K(self):
        out = pt.main(["--K", "50", "--tau", "0.4", "--delay", "0.1", "--method", "sweep"])
        self.assertEqual(out, 0)


class PidTests(unittest.TestCase):
    PLANT = dict(K=1.0, tau=0.4, delay=0.1, integrating=True)

    def test_plant_step_converges(self):
        p = pt.Plant(2.0, 0.3, 0.0, False)
        y = 0.0
        for _ in range(1000):
            y = p.step(1.0)
        self.assertAlmostEqual(y, 2.0, places=2)

    def test_ultimate_gain_and_zn(self):
        plant = pt.Plant(**self.PLANT)
        r = pt.ultimate_gain(plant)
        self.assertIsNotNone(r)
        ku, pu = r
        self.assertGreater(ku, 0.5)
        self.assertGreater(pu, 0.2)
        g = pt.zn_gains(ku, pu, "some_overshoot")
        c, m = pt.cost(plant, g)
        self.assertFalse(m["diverged"])
        self.assertIsNotNone(m["settling_time_s"])
        self.assertLess(m["overshoot_pct"], 80)

    def test_no_ultimate_gain_for_pure_lag(self):
        self.assertIsNone(pt.ultimate_gain(pt.Plant(1.0, 0.5, 0.0, False)))

    def test_twiddle_improves(self):
        plant = pt.Plant(**self.PLANT)
        start = {"kp": 0.5, "ki": 0.0, "kd": 0.0}
        c0 = pt.cost(plant, start)[0]
        g, c1 = pt.twiddle(plant, start, max_iter=60)
        self.assertLess(c1, c0)
        self.assertLess(pt.cost(plant, g)[1]["overshoot_pct"], 40)

    def test_sweep_sorted_and_avoids_unstable(self):
        plant = pt.Plant(**self.PLANT)
        rows = pt.gain_sweep(plant, [0.5, 2, 50], [0.0], [0.0, 0.1])
        self.assertEqual([r[0] for r in rows], sorted(r[0] for r in rows))
        self.assertNotEqual(rows[0][1]["kp"], 50)

    def test_step_metrics_divergence(self):
        ts, ys, _ = pt.simulate_step(pt.Plant(**self.PLANT), 500.0, T=5.0)
        self.assertTrue(pt.step_metrics(ts, ys)["diverged"])


if __name__ == "__main__":
    unittest.main()
