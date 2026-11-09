"""Chequeo de lectura real del MCP de Unreal 5.8 (paso 2 del preflight). Solo lee.

Hace, en orden: ping jsonrpc válido, initialize (sesión), SceneTools.get_current_level (qué proyecto
y mapa responde) y EditorAppToolset.IsPIERunning. Verificado en la máquina de prueba (laptop, GTX 1660 Ti) (8-nov-2026):
list_toolsets NO trae _meta con projectName/engineVersion y serverInfo llega vacío, por eso el
proyecto se reconoce por la ruta del nivel actual (o por el log).

Uso: python mcp_check.py [--expect-map /Game/Maps/X] [--url http://127.0.0.1:8123/mcp]
Variables: UE_MCP_URL. Salida: líneas "MCP ...", "NIVEL ...", "PIE ..." y al final VERDE, AMARILLO o ROJO.
Código 0 verde, 1 amarillo, 2 rojo (no responde).
"""
import importlib.util
import os
import sys
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = "editor_toolset.toolsets.scene.SceneTools"
APP = "EditorToolset.EditorAppToolset"


def _load_client():
    path = os.path.normpath(os.path.join(HERE, "..", "..", "ue-viewport-eyes", "scripts", "ue_capture.py"))
    spec = importlib.util.spec_from_file_location("ue_capture", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def level_text(ret):
    """Pura. get_current_level devuelve la ruta como string o dentro de un dict."""
    if isinstance(ret, str):
        return ret
    if isinstance(ret, dict):
        for k in ("path", "level", "name", "returnValue"):
            if isinstance(ret.get(k), str):
                return ret[k]
    return str(ret)


def verdict(level, expect, pie):
    """Pura. (semáforo, motivos). Untitled o mapa distinto = amarillo; PIE corriendo = amarillo."""
    why = []
    if "/Temp/Untitled" in level:
        why.append("el editor esta en un mapa sin guardar (/Temp/Untitled): ver si arranco en el mapa pedido")
    if expect and expect not in level:
        why.append("el nivel no es el esperado (%s): puede haber otro editor en el mismo puerto" % expect)
    if pie:
        why.append("hay PIE corriendo: no editar assets hasta cerrarlo")
    return ("AMARILLO" if why else "VERDE"), why


def main(argv):
    uc = _load_client()
    url = argv[argv.index("--url") + 1] if "--url" in argv else None
    expect = argv[argv.index("--expect-map") + 1] if "--expect-map" in argv else None
    mcp = uc.Mcp(url, timeout=30)
    try:
        if not mcp.ping():
            print("MCP responde al ping con error en %s" % mcp.url)
            print("ROJO")
            return 2
        print("MCP OK %s" % mcp.url)
        level = level_text(mcp.call("get_current_level", {}, SCENE))
        print("NIVEL %s" % level)
        pie = bool(mcp.call("IsPIERunning", {}, APP))
        print("PIE %s" % ("corriendo" if pie else "no"))
    except (urllib.error.URLError, OSError) as e:
        print("MCP no responde en %s (%s). Causas: servidor sin iniciar, otro puerto, editor compilando." % (mcp.url, e))
        print("ROJO")
        return 2
    except ValueError as e:
        print("MCP respondio pero la herramienta fallo: %s" % e)
        print("AMARILLO")
        return 1
    color, why = verdict(level, expect, pie)
    for w in why:
        print("  - " + w)
    print(color)
    return 0 if color == "VERDE" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
