"""Pruebas de ue-render-shots sin Unreal: plan, encuadre, veredicto, trabajos de alta resolución,
máquina de estados del script de editor y captura contra un servidor MCP falso.
Correr: python -I .claude/skills/ue-render-shots/tests/test_render_shots.py"""
import base64
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import threading
import unittest
import zlib
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import render_plan as rp  # noqa: E402
import render_shots as rs  # noqa: E402
import editor_highres as eh  # noqa: E402

EXAMPLE = os.path.join(HERE, "..", "templates", "subjects.example.json")


def make_png(w, h):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class Plan(unittest.TestCase):
    def test_ejemplo_completo(self):
        plan = rp.build_plan(json.load(open(EXAMPLE, encoding="utf-8")))
        names = [s["name"] for s in plan]
        self.assertEqual(names[0], "hero_ModeloA")
        self.assertEqual(sum(n.startswith("turn_") for n in names), 8)
        self.assertIn("lineup", names)
        self.assertEqual(sum(n.startswith("close_") for n in names), 3)
        self.assertIn("accion_picada", names)
        self.assertEqual(len(names), len(set(names)))

    def test_encuadre_entra_en_cuadro(self):
        d = rp.fit_distance(100, 90, 16 / 9, 1.0)
        half_v = math.radians(rp.vfov_deg(90, 16 / 9) / 2)
        self.assertAlmostEqual(math.asin(100 / d), half_v, places=6)  # toca justo el borde vertical
        self.assertGreater(rp.fit_distance(100, 90, 16 / 9, 1.2), d)

    def test_camara_mira_al_centro(self):
        c = [10, 20, 30]
        loc, rot = rp.look_pose(c, 500, 35, 20)
        self.assertAlmostEqual(math.dist(loc, c), 500, places=6)
        yaw = math.degrees(math.atan2(c[1] - loc[1], c[0] - loc[0])) % 360
        self.assertAlmostEqual(yaw, rot[1], places=6)
        self.assertEqual(rot[0], -20.0)

    def test_lineup_contiene_a_todos(self):
        subs = [{"name": "a", "center": [0, 0, 0], "radius": 50}, {"name": "b", "center": [1000, 0, 0], "radius": 100}]
        c, r = rp.group_sphere(subs)
        for s in subs:
            self.assertLessEqual(math.dist(c, s["center"]) + s["radius"], r + 1e-9)

    def test_errores(self):
        bad = {"subjects": [{"name": "a b", "center": [0, 0], "radius": 0}], "shots": ["hero"]}
        with self.assertRaises(ValueError) as cm:
            rp.build_plan(bad)
        msg = str(cm.exception)
        self.assertIn("nombre invalido", msg)
        self.assertIn("center", msg)
        self.assertIn("radius", msg)
        ok = {"subjects": [{"name": "a", "center": [0, 0, 0], "radius": 1}]}
        for shots in (["foto"], ["turntable:1"], [{"name": "x"}], ["hero", "hero"]):
            with self.assertRaises(ValueError, msg=shots):
                rp.build_plan(dict(ok, shots=shots))


class Pure(unittest.TestCase):
    def test_res(self):
        self.assertEqual(rs.parse_res("1920x1080"), (1920, 1080))
        for bad in ("1920", "0x10", "ax b"):
            with self.assertRaises(ValueError):
                rs.parse_res(bad)

    def test_sujeto_desde_caja(self):
        s = rs.subject_from_box("A", {"min": {"x": -100, "y": -50, "z": 0}, "max": {"x": 100, "y": 50, "z": 200}})
        self.assertEqual(s["center"], [0.0, 0.0, 100.0])
        self.assertAlmostEqual(s["radius"], math.dist((-100, -50, 0), (100, 50, 200)) / 2, places=1)
        with self.assertRaises(ValueError):
            rs.subject_from_box("V", {"min": {"x": 0, "y": 0, "z": 0}, "max": {"x": 0, "y": 0, "z": 0}})
        self.assertEqual(rs.actor_name("/Game/Maps/D.D:PersistentLevel.SM_Avion_0"), "SM_Avion_0")

    def test_veredicto(self):
        ok = {"ok": True, "size": [1920, 1080]}
        low = {"ok": True, "size": [1912, 862]}
        self.assertEqual(rs.verdict([ok], 1920, 1080), (0, "RENDER_OK"))
        self.assertEqual(rs.verdict([ok, low], 1920, 1080), (3, "RENDER_LOWRES"))
        self.assertEqual(rs.verdict([ok, {"ok": False, "size": None}], 1920, 1080), (1, "RENDER_FAIL"))
        self.assertEqual(rs.verdict([], 1920, 1080)[1], "RENDER_FAIL")

    def test_trabajos_highres(self):
        jobs = rs.highres_jobs([{"name": "hero", "loc": [1, 2, 3], "rot": [-10, 90, 0]}], "C:\\out", 2560, 1440)
        self.assertEqual(jobs[0]["cmd"], "HighResShot 2560x1440 filename=C:/out/hero.png")
        self.assertEqual(jobs[0]["png"], "C:/out/hero.png")


class EditorStateMachine(unittest.TestCase):
    def test_ciclo_por_toma(self):
        st = {"i": 0, "phase": "move", "ticks": 0}
        actions = []
        for _ in range(eh.SETTLE_TICKS + 5):
            st, a = eh.next_step(st, png_exists=False)
            actions.append(a)
        self.assertEqual(actions[0], "move")
        self.assertEqual(actions.count("shoot"), 1)
        st, a = eh.next_step(st, png_exists=True)
        self.assertEqual((a, st["i"], st["phase"]), ("done_ok", 1, "move"))

    def test_timeout(self):
        st = {"i": 0, "phase": "wait", "ticks": eh.TIMEOUT_TICKS - 1}
        st, a = eh.next_step(st, png_exists=False)
        self.assertEqual((a, st["i"]), ("done_fail", 1))


class FakeMcp(BaseHTTPRequestHandler):
    size = (1920, 1080)

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        res = {}
        if body.get("method") == "tools/call":
            a = body["params"]["arguments"]
            if a["tool_name"] == "CaptureViewport":
                ret = {"image": {"data": base64.b64encode(make_png(*FakeMcp.size)).decode()}}
            else:  # get_actor_bounds
                ret = {"min": {"x": -50, "y": -50, "z": 0}, "max": {"x": 50, "y": 50, "z": 100}}
            res = {"content": [{"type": "text", "text": json.dumps({"returnValue": ret})}]}
        data = json.dumps({"jsonrpc": "2.0", "id": body.get("id"), "result": res}).encode()
        self.send_response(200)
        self.send_header("Mcp-Session-Id", "s1")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class AgainstFake(unittest.TestCase):
    def setUp(self):
        self.srv = HTTPServer(("127.0.0.1", 0), FakeMcp)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.shutdown)
        os.environ["UE_MCP_URL"] = "http://127.0.0.1:%d/mcp" % self.srv.server_port
        self.addCleanup(os.environ.pop, "UE_MCP_URL", None)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.plan = os.path.join(self.tmp, "plan.json")
        json.dump(rp.build_plan({"subjects": [{"name": "A", "center": [0, 0, 0], "radius": 100}],
                                 "shots": ["hero", "turntable:4"]}), open(self.plan, "w"))

    def test_capture_ok_y_manifest(self):
        FakeMcp.size = (1920, 1080)
        out = os.path.join(self.tmp, "r")
        self.assertEqual(rs.main(["x", "capture", self.plan, "--out", out]), 0)
        man = json.load(open(os.path.join(out, "manifest.json")))
        self.assertEqual(man["result"], "RENDER_OK")
        self.assertEqual(len(man["shots"]), 5)

    def test_capture_baja_resolucion(self):
        FakeMcp.size = (1912, 862)  # tamaño real del viewport en la laptop de prueba
        self.assertEqual(rs.main(["x", "capture", self.plan, "--out", os.path.join(self.tmp, "r2")]), 3)

    def test_bounds(self):
        out = os.path.join(self.tmp, "subjects.json")
        self.assertEqual(rs.main(["x", "bounds", "/Game/Maps/D.D:PersistentLevel.Cubo_0", "--out", out]), 0)
        data = json.load(open(out))
        self.assertEqual(data["subjects"][0]["name"], "Cubo_0")
        self.assertEqual(data["subjects"][0]["center"], [0.0, 0.0, 50.0])
        self.assertTrue(rp.build_plan(data))


if __name__ == "__main__":
    unittest.main()
