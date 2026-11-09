"""Configuración única del editor a través del servidor MCP de Epic (el editor debe estar abierto con -ModelContextProtocolStartServer):
  1. Ejecución remota de Python activada (Project > Plugins > Python > bRemoteExecution) para que upy.py pueda correr Python en el editor.
  2. "Use Less CPU when in Background" apagado; si no, PIE corre a 3 fps cuando el editor no tiene foco y las pruebas dan resultados falsos.
Uso: python setup_editor.py [--url http://127.0.0.1:8123/mcp]
Imprime SETUP_OK, o SETUP_FAIL <motivo>. Requiere el PythonScriptPlugin habilitado en el .uproject.
Verificado en un proyecto C++ vacío de UE 5.8.4 (KitSmokeTest, 9-nov-2026)."""
import argparse, json, os, sys, urllib.request

def post(url, payload, sid=None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    if sid:
        req.add_header("Mcp-Session-Id", sid)
    with urllib.request.urlopen(req, timeout=60) as r:
        new_sid = r.headers.get("Mcp-Session-Id")
        body = r.read().decode("utf-8", "replace")
    if "data:" in body:
        body = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")][-1]
    return new_sid, (json.loads(body) if body.strip() else {})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("UE_MCP_URL", "http://127.0.0.1:8123/mcp"))
    a = ap.parse_args()
    try:
        sid, _ = post(a.url, {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "setup_editor", "version": "1"}}})
        post(a.url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    except Exception as e:
        print("SETUP_FAIL MCP not reachable at %s (%s). Start the editor with -ModelContextProtocolStartServer." % (a.url, e))
        return 1
    ts = "ConfigSettingsToolset.ConfigSettingsToolset"
    steps = [
        ("Project", "Plugins", "Python", {"bRemoteExecution": True}),
        ("Editor", "General", "EditorPerformanceSettings", {"bThrottleCPUWhenNotForeground": False}),
    ]
    for i, (c, cat, sec, vals) in enumerate(steps, 1):
        args = {"containerName": c, "categoryName": cat, "sectionName": sec}
        for tool, extra in (("SetSectionProperties", {"propertiesJson": json.dumps(vals)}), ("SaveSection", {})):
            _, res = post(a.url, {"jsonrpc": "2.0", "id": i * 10 + len(extra), "method": "tools/call", "params": {
                "name": "call_tool", "arguments": {"toolset_name": ts, "tool_name": tool, "arguments": dict(args, **extra)}}}, sid)
            r = res.get("result", {})
            text = " ".join(x.get("text", "") for x in r.get("content", []) if isinstance(x, dict))
            if res.get("error") or r.get("isError") or "rror" in text[:200]:
                print("SETUP_FAIL %s %s/%s/%s: %s" % (tool, c, cat, sec, (text or json.dumps(res))[:300]))
                return 1
        print("set %s/%s/%s %s" % (c, cat, sec, vals))
    print("SETUP_OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
