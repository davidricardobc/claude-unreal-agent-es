"""Prueba de funciones puras con datos ficticios. Correr: python tests/test_playtest.py"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import analyze_playtest as a  # noqa: E402
import telemetry_logger as tl  # noqa: E402

# outliers: un valor claramente fuera
o = a.outliers({"a": 10, "b": 11, "c": 9, "d": 10, "e": 40}, z=2.0)
assert list(o) == ["e"] and o["e"] > 0, o
assert a.outliers({"a": 1, "b": 1}) == {}

ev, files = a.load_events([os.path.join(HERE, "..", "examples", "sample_telemetry.csv")])
S = a.summarize(ev, min_n=1)
assert S["deaths_total"] == 2 and S["deaths_by_cause"] == {"sword": 1, "storm": 1}
assert S["time_to_first_death_s"]["median"] == 22.5, S["time_to_first_death_s"]  # 20 s y 25 s desde el inicio de cada ronda
assert S["use_by_subject"] == {"sword": 2, "bow": 1}
assert S["win_rate"]["loadout_a"] == {"rate": 1.0, "n": 2} and S["win_rate"]["loadout_b"]["rate"] == 0.0

# propuestas: con datos sintéticos, un arma domina el daño
fake = []
for i, (w, d) in enumerate([("a", 10), ("b", 11), ("c", 9), ("d", 10), ("e", 80)]):
    fake.append({"ts": float(i), "session": "S", "build": "b", "round": "1", "player_id": "p",
                 "event": "damage", "subject": w, "value": float(d)})
S2 = a.summarize(fake, z=2.0, min_n=1)
props = a.propose(S2)
assert [p[0] for p in props] == ["e"] and "reducir" in props[0][2], props
md = a.render(S2, props, ["x.csv"])
assert "BORRADOR" in md and "[ ]" in md and "| 1 | e |" in md

with tempfile.TemporaryDirectory() as d:
    t = [0.0]
    log = tl.TelemetryLogger(d, build="t", session="SX", clock=lambda: t[0])
    t[0] = 1.5
    log.event("death", player_id="p1", subject="a,b", value=1, round=2)
    log.close()
    ev2, _ = a.load_events([d])
    assert len(ev2) == 1 and ev2[0]["subject"] == "a,b" and ev2[0]["ts"] == 1.5 and ev2[0]["round"] == "2"
    out = os.path.join(d, "out", "s.md")
    assert a.main([d, "--out", out, "--min-n", "1"]) == 0 and os.path.getsize(out) > 100

# I5: MAD = 0 no oculta el outlier obvio
o = a.outliers({"a": 10, "b": 10, "c": 10, "d": 10, "e": 80})
assert list(o) == ["e"], o
assert a.outliers({"a": 5, "b": 5, "c": 5}) == {}  # todo igual: sin outliers
assert a.outliers({"a": 1, "b": 99}) == {}  # menos de 3 valores

# I6: con 2 loadouts la prueba binomial sí propone; n chico no
wr = {"A": {"rate": 0.9, "n": 10}, "B": {"rate": 0.1, "n": 10}}
w = a.win_rate_outliers(wr, 10, 20)
assert set(w) == {"A", "B"} and w["A"] > 0 > w["B"], w
assert a.win_rate_outliers(wr, 10, 20, min_n=11) == {}
assert a.win_rate_outliers({"A": {"rate": 0.55, "n": 10}, "B": {"rate": 0.45, "n": 10}}, 10, 20) == {}
assert a.win_rate_outliers({}, 0, 0) == {}
ev3 = []
for i in range(10):
    for who, win in (("A", 1 if i < 9 else 0), ("B", 0 if i < 9 else 1)):
        ev3.append({"ts": float(i), "session": "S", "build": "b", "round": "1", "player_id": who,
                    "event": "round_end", "subject": who, "value": float(win)})
S3 = a.summarize(ev3, z=2.0, min_n=5)
pr3 = a.propose(S3)
assert {p[0] for p in pr3} == {"A", "B"}, pr3
print("KIT_OK test_playtest")
