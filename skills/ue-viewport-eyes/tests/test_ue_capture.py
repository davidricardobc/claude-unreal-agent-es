"""Pruebas de scripts/ue_capture.py. Sin Unreal: partes puras y un servidor MCP falso en localhost."""
import base64
import json
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
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import ue_capture as uc  # noqa: E402


def make_png(w, h):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class Pure(unittest.TestCase):
    def test_orbit_front_mira_al_centro(self):
        loc, rot = uc.orbit_pose((100, 0, 0), 100, 0, 0, factor=2)
        self.assertAlmostEqual(loc[0], 300)
        self.assertAlmostEqual(loc[1], 0)
        self.assertEqual(rot, (-0.0, 180.0, 0.0))

    def test_orbit_top_queda_arriba_y_mira_abajo(self):
        loc, rot = uc.orbit_pose((0, 0, 0), 100, 0, 80)
        self.assertGreater(loc[2], 170)
        self.assertEqual(rot[0], -80.0)

    def test_capture_args_siempre_con_annotations(self):
        a = uc.capture_args((1, 2, 3), (-10, 90))
        self.assertFalse(a["bShowUI"])
        self.assertEqual(a["annotations"]["maxLabels"], 0)
        self.assertEqual(a["captureTransform"]["location"], {"x": 1, "y": 2, "z": 3})
        self.assertEqual(a["captureTransform"]["rotation"], {"pitch": -10, "yaw": 90, "roll": 0.0})
        self.assertNotIn("captureTransform", uc.capture_args())

    def test_payload_usa_call_tool_con_toolset_largo(self):
        p = uc.call_payload("CaptureViewport", {"x": 1}, 7)
        args = p["params"]["arguments"]
        self.assertEqual(p["params"]["name"], "call_tool")
        self.assertEqual(args["toolset_name"], "EditorToolset.EditorAppToolset")
        self.assertEqual(args["tool_name"], "CaptureViewport")

    def test_tool_return_y_imagen_de_los_dos_tipos(self):
        png = make_png(4, 3)
        b64 = base64.b64encode(png).decode()
        vp = {"result": {"content": [{"type": "text", "text": json.dumps(
            {"returnValue": {"image": {"mimeType": "image/png", "data": b64}, "cameraFOV": 90}})}]}}
        ed = {"result": {"content": [{"type": "text", "text": json.dumps({"returnValue": {"data": b64}})}]}}
        self.assertEqual(uc.png_size(uc.image_bytes(uc.tool_return(vp))), (4, 3))
        self.assertEqual(uc.image_bytes(uc.tool_return(ed)), png)

    def test_errores_claros(self):
        with self.assertRaises(ValueError):
            uc.tool_return({"error": {"code": -1}})
        with self.assertRaises(ValueError):
            uc.tool_return({"result": {"isError": True, "content": []}})
        with self.assertRaises(ValueError):
            uc.image_bytes({"image": {"data": ""}})
        with self.assertRaises(ValueError):
            uc.png_size(b"GIF89a....................")

    def test_sse(self):
        self.assertEqual(uc.parse_sse_or_json('event: message\ndata: {"a": 1}\n'), {"a": 1})
        self.assertEqual(uc.parse_sse_or_json(""), {})

    def test_parse_triplet(self):
        self.assertEqual(uc.parse_triplet("-10,90"), (-10.0, 90.0, 0.0))
        with self.assertRaises(ValueError):
            uc.parse_triplet("1")


class FakeMcp(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeMcp.calls.append((body.get("method"), self.headers.get("Mcp-Session-Id"), body))
        if body.get("method") == "initialize":
            out = {"jsonrpc": "2.0", "id": 0, "result": {}}
        elif body.get("method") == "tools/call":
            png = base64.b64encode(make_png(1920, 1080)).decode()
            text = json.dumps({"returnValue": {"image": {"data": png}}})
            out = {"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"type": "text", "text": text}]}}
        else:
            out = {"jsonrpc": "2.0", "id": body.get("id"), "result": {}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Mcp-Session-Id", "s-123")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class AgainstFakeServer(unittest.TestCase):
    def setUp(self):
        FakeMcp.calls = []
        self.srv = HTTPServer(("127.0.0.1", 0), FakeMcp)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.shutdown)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["UE_MCP_URL"] = "http://127.0.0.1:%d/mcp" % self.srv.server_port
        self.addCleanup(os.environ.pop, "UE_MCP_URL", None)

    def test_orbit_guarda_4_png_y_cams(self):
        code = uc.main(["x", "orbit", "--out", self.tmp, "--center", "0,0,100", "--radius", "200"])
        self.assertEqual(code, 0)
        for n in ("front", "tq", "side", "top"):
            self.assertTrue(os.path.isfile(os.path.join(self.tmp, n + ".png")))
        cams = json.load(open(os.path.join(self.tmp, "cams.json")))
        self.assertEqual(cams["cams"]["top"]["size"], [1920, 1080])
        methods = [m for m, _, _ in FakeMcp.calls]
        self.assertEqual(methods[0], "ping")
        self.assertIn("initialize", methods)
        tool_calls = [(sid, b) for m, sid, b in FakeMcp.calls if m == "tools/call"]
        self.assertEqual(len(tool_calls), 4)
        self.assertTrue(all(sid == "s-123" for sid, _ in tool_calls))  # manda la sesión

    def test_sin_servidor_da_2(self):
        os.environ["UE_MCP_URL"] = "http://127.0.0.1:1/mcp"
        self.assertEqual(uc.main(["x", "ping"]), 2)


if __name__ == "__main__":
    unittest.main()
