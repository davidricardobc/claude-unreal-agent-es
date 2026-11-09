"""Capturas del editor de Unreal 5.8 por el MCP de Epic (EditorAppToolset). Sin Python dentro de UE.

Herramientas usadas (EditorAppToolset.h de UE 5.8, probadas en la máquina de prueba el 8-nov-2026):
  CaptureViewport(CaptureTransform, Annotations, bShowUI=false) -> PNG base64 del viewport del editor.
     En la práctica exige captureTransform y annotations aunque digan opcionales.
     La resolución es la del viewport (en la laptop de prueba, 1912x862): no se puede pedir otra.
  CaptureEditorImage() -> PNG de toda la ventana del editor (sirve en PIE: incluye el HUD).
  IsPIERunning() -> bool.
Toolset: "EditorToolset.EditorAppToolset". Las llamadas van por la metaherramienta call_tool
(toolset_name, tool_name, arguments) con la cabecera Mcp-Session-Id que da initialize.

Uso (editor abierto con el MCP, ver ue-session-preflight):
  python ue_capture.py ping
  python ue_capture.py orbit --out <dir> --center X,Y,Z --radius R [--angles front,tq,side,top] [--factor 1.8]
  python ue_capture.py one --out <archivo.png> --loc X,Y,Z --rot PITCH,YAW[,ROLL]
  python ue_capture.py editor --out <archivo.png>        (PIE con HUD, o la ventana completa)
Variables: UE_MCP_URL (por defecto http://127.0.0.1:8123/mcp).
Salida: una línea "OK <archivo> <ancho>x<alto>" por imagen y cams.json en modo orbit. Código 0 si todo
salió, 1 si alguna falló, 2 si no responde el MCP.
"""
import base64
import json
import math
import os
import struct
import sys
import urllib.error
import urllib.request

TOOLSET = "EditorToolset.EditorAppToolset"
DEFAULT_URL = "http://127.0.0.1:8123/mcp"

# Nombre: (azimut, elevación) en grados. Mismos de la tabla del SKILL.md.
ANGLES = {"front": (0, 15), "tq": (45, 35), "side": (90, 10), "top": (0, 80)}

# Anotaciones apagadas: sin rejilla ni etiquetas (foto limpia). Hay que mandarlas igual.
NO_ANNOTATIONS = {"gridSpacing": 0, "gridExtent": 0, "gridHeight": 0,
                  "maxLabelDistance": 0, "classFilter": None, "maxLabels": 0}


# ---------- partes puras (con pruebas) ----------

def orbit_pose(center, radius, az_deg, el_deg, factor=1.8):
    """Cámara a distancia factor*radius de center, mirando a center.
    Devuelve ((x, y, z), (pitch, yaw, roll)) en cm y grados de UE (pitch negativo = mira abajo)."""
    d = factor * float(radius)
    az, el = math.radians(az_deg), math.radians(el_deg)
    cx, cy, cz = center
    loc = (cx + d * math.cos(el) * math.cos(az),
           cy + d * math.cos(el) * math.sin(az),
           cz + d * math.sin(el))
    yaw = (az_deg + 180.0) % 360.0
    return loc, (-float(el_deg), yaw, 0.0)


def transform_json(loc, rot):
    x, y, z = loc
    pitch, yaw = rot[0], rot[1]
    roll = rot[2] if len(rot) > 2 else 0.0
    return {"location": {"x": x, "y": y, "z": z},
            "rotation": {"pitch": pitch, "yaw": yaw, "roll": roll}}


def capture_args(loc=None, rot=None, show_ui=False, annotations=None):
    """Argumentos de CaptureViewport. Sin loc usa la cámara actual del viewport (sin verificar)."""
    args = {"bShowUI": bool(show_ui), "annotations": annotations or dict(NO_ANNOTATIONS)}
    if loc is not None:
        args["captureTransform"] = transform_json(loc, rot or (0.0, 0.0, 0.0))
    return args


def call_payload(tool, args, req_id=1, toolset=TOOLSET):
    return {"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
            "params": {"name": "call_tool",
                       "arguments": {"toolset_name": toolset, "tool_name": tool, "arguments": args}}}


def parse_sse_or_json(body):
    """El servidor puede responder JSON o text/event-stream: tomar el último data:."""
    if body.startswith("event:") or body.startswith("data:") or "\ndata:" in body:
        lines = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")]
        body = lines[-1] if lines else "{}"
    return json.loads(body) if body.strip() else {}


def tool_return(response):
    """Saca returnValue del texto de la respuesta de call_tool. Lanza ValueError con el motivo."""
    if "error" in response:
        raise ValueError("error MCP: %s" % json.dumps(response["error"])[:300])
    res = response.get("result", {})
    if res.get("isError"):
        raise ValueError("la herramienta fallo: %s" % json.dumps(res.get("content"))[:300])
    for c in res.get("content", []):
        if c.get("type") == "text":
            data = json.loads(c["text"])
            return data.get("returnValue", data)
    if res.get("structuredContent"):
        sc = res["structuredContent"]
        return sc.get("returnValue", sc)
    raise ValueError("respuesta sin contenido")


def image_bytes(ret):
    """PNG de CaptureViewport (returnValue.image.data) o de CaptureEditorImage (returnValue.data)."""
    img = ret.get("image", ret) if isinstance(ret, dict) else {}
    data = img.get("data") or img.get("Data")
    if not data:
        raise ValueError("la respuesta no trae imagen (viewport minimizado o PIE cargando?)")
    return base64.b64decode(data)


def png_size(raw):
    """(ancho, alto) leyendo el encabezado IHDR del PNG. Lanza ValueError si no es PNG."""
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError("no es un PNG")
    return struct.unpack(">II", raw[16:24])


def parse_triplet(text, n=3):
    vals = [float(v) for v in text.split(",")]
    if len(vals) < 2 or len(vals) > n:
        raise ValueError("se esperaban hasta %d numeros separados por coma: %s" % (n, text))
    return tuple(vals + [0.0] * (n - len(vals)))


# ---------- red (necesita el editor abierto) ----------

class Mcp:
    def __init__(self, url=None, timeout=120):
        self.url = url or os.environ.get("UE_MCP_URL", DEFAULT_URL)
        self.timeout = timeout
        self.session = None
        self._id = 0

    def _post(self, payload):
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers={
            "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
        if self.session:
            req.add_header("Mcp-Session-Id", self.session)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            sid = r.headers.get("Mcp-Session-Id")
            body = r.read().decode("utf-8", "replace")
        return sid, parse_sse_or_json(body)

    def ping(self):
        """Ping jsonrpc válido (un {} vacío hace que el servidor loguee un error)."""
        _, res = self._post({"jsonrpc": "2.0", "id": 99, "method": "ping"})
        return "error" not in res

    def start(self):
        sid, _ = self._post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "ue-viewport-eyes", "version": "1"}}})
        self.session = sid
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, tool, args, toolset=TOOLSET):
        if self.session is None:
            self.start()
        self._id += 1
        _, res = self._post(call_payload(tool, args, self._id, toolset))
        return tool_return(res)


def save_png(raw, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(raw)
    w, h = png_size(raw)
    print("OK %s %dx%d" % (path, w, h))
    return w, h


def capture_viewport(mcp, path, loc=None, rot=None, show_ui=False):
    return save_png(image_bytes(mcp.call("CaptureViewport", capture_args(loc, rot, show_ui))), path)


def capture_editor(mcp, path):
    return save_png(image_bytes(mcp.call("CaptureEditorImage", {})), path)


def orbit(mcp, out_dir, center, radius, names, factor=1.8):
    cams, fails = {}, 0
    for name in names:
        if name not in ANGLES:
            print("FAIL angulo desconocido: %s (usar %s)" % (name, ",".join(ANGLES)))
            fails += 1
            continue
        loc, rot = orbit_pose(center, radius, *ANGLES[name], factor=factor)
        try:
            w, h = capture_viewport(mcp, os.path.join(out_dir, name + ".png"), loc, rot)
            cams[name] = {"loc": loc, "rot": rot, "size": [w, h]}
        except (ValueError, urllib.error.URLError, OSError) as e:
            print("FAIL %s: %s" % (name, e))
            fails += 1
    with open(os.path.join(out_dir, "cams.json"), "w", encoding="utf-8") as f:
        json.dump({"center": center, "radius": radius, "factor": factor, "cams": cams}, f, indent=1)
    return fails == 0


def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv):
    if len(argv) < 2 or argv[1] not in ("ping", "orbit", "one", "editor"):
        print(__doc__)
        return 1
    mcp = Mcp()
    try:
        if not mcp.ping():
            print("FAIL el MCP respondio con error al ping: %s" % mcp.url)
            return 2
    except (urllib.error.URLError, OSError) as e:
        print("FAIL no responde el MCP en %s (%s). Correr ue-session-preflight." % (mcp.url, e))
        return 2
    cmd = argv[1]
    if cmd == "ping":
        print("OK MCP responde en " + mcp.url)
        return 0
    out = _arg(argv, "--out")
    if not out:
        print("FAIL falta --out")
        return 1
    try:
        if cmd == "orbit":
            center = parse_triplet(_arg(argv, "--center", "0,0,0"))
            radius = float(_arg(argv, "--radius", "500"))
            names = _arg(argv, "--angles", "front,tq,side,top").split(",")
            return 0 if orbit(mcp, out, center, radius, names, float(_arg(argv, "--factor", "1.8"))) else 1
        if cmd == "one":
            loc = parse_triplet(_arg(argv, "--loc", "0,0,0"))
            rot = parse_triplet(_arg(argv, "--rot", "0,0,0"))
            capture_viewport(mcp, out, loc, rot, "--ui" in argv)
            return 0
        capture_editor(mcp, out)
        return 0
    except (ValueError, urllib.error.URLError, OSError) as e:
        print("FAIL %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
