"""Pruebas de scripts/mcp_check.py: partes puras y un servidor MCP falso. Sin Unreal."""
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import mcp_check as mc  # noqa: E402


class Pure(unittest.TestCase):
    def test_level_text(self):
        self.assertEqual(mc.level_text("/Game/Maps/A.A"), "/Game/Maps/A.A")
        self.assertEqual(mc.level_text({"path": "/Game/Maps/B"}), "/Game/Maps/B")

    def test_verdict(self):
        self.assertEqual(mc.verdict("/Game/Maps/A.A", "/Game/Maps/A", False), ("VERDE", []))
        self.assertEqual(mc.verdict("/Temp/Untitled_1", None, False)[0], "AMARILLO")
        self.assertEqual(mc.verdict("/Game/Maps/B", "/Game/Maps/A", False)[0], "AMARILLO")
        self.assertEqual(mc.verdict("/Game/Maps/A", None, True)[0], "AMARILLO")


class Fake(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.seen.append(body)
        res = {}
        if body.get("method") == "tools/call":
            a = body["params"]["arguments"]
            val = "/Game/Maps/Demo.Demo" if a["tool_name"] == "get_current_level" else False
            res = {"content": [{"type": "text", "text": json.dumps({"returnValue": val})}]}
        data = json.dumps({"jsonrpc": "2.0", "id": body.get("id"), "result": res}).encode()
        self.send_response(200)
        self.send_header("Mcp-Session-Id", "abc")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class AgainstFake(unittest.TestCase):
    def test_verde_y_toolsets_correctos(self):
        Fake.seen = []
        srv = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        url = "http://127.0.0.1:%d/mcp" % srv.server_port
        self.assertEqual(mc.main(["x", "--url", url, "--expect-map", "/Game/Maps/Demo"]), 0)
        self.assertEqual(Fake.seen[0], {"jsonrpc": "2.0", "id": 99, "method": "ping"})
        calls = [b["params"]["arguments"] for b in Fake.seen if b.get("method") == "tools/call"]
        self.assertEqual(calls[0]["toolset_name"], "editor_toolset.toolsets.scene.SceneTools")
        self.assertEqual(calls[1]["toolset_name"], "EditorToolset.EditorAppToolset")
        self.assertEqual(calls[1]["tool_name"], "IsPIERunning")

    def test_rojo_sin_servidor(self):
        self.assertEqual(mc.main(["x", "--url", "http://127.0.0.1:1/mcp"]), 2)


if __name__ == "__main__":
    unittest.main()
