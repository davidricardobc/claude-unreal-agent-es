"""Cliente MCP mínimo para el editor de Unreal. Uso:
  python mcp.py toolsets
  python mcp.py describe <toolset>
  python mcp.py call <toolset> <tool> '<json args>'
  python mcp.py py <file.py>      (ejecuta Python en el editor con ProgrammaticToolset.execute_tool_script)
"""
import json, sys, urllib.request, os

URL = os.environ.get("UE_MCP_URL", "http://127.0.0.1:8123/mcp")
SESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_session.txt")
_id = [0]

def post(payload, session=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=data, headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    if session:
        req.add_header("Mcp-Session-Id", session)
    with urllib.request.urlopen(req, timeout=600) as r:
        sid = r.headers.get("Mcp-Session-Id")
        body = r.read().decode("utf-8", "replace")
    if body.startswith("event:") or "\ndata:" in body or body.startswith("data:"):
        lines = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")]
        body = lines[-1] if lines else "{}"
    return sid, (json.loads(body) if body.strip() else {})

def session():
    if os.path.exists(SESS):
        return open(SESS).read().strip()
    sid, _ = post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "unreal-agent", "version": "1"}}})
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    open(SESS, "w").write(sid or "")
    return sid

def tool(name, args):
    sid = session()
    _id[0] += 1
    try:
        _, res = post({"jsonrpc": "2.0", "id": _id[0], "method": "tools/call", "params": {"name": name, "arguments": args}}, sid)
    except urllib.error.HTTPError as e:
        if e.code in (400, 404) and os.path.exists(SESS):
            os.remove(SESS)
            sid = session()
            _, res = post({"jsonrpc": "2.0", "id": _id[0], "method": "tools/call", "params": {"name": name, "arguments": args}}, sid)
        else:
            raise
    return res

def show(res):
    r = res.get("result", res)
    for c in r.get("content", []) if isinstance(r, dict) else []:
        if c.get("type") == "text":
            print(c["text"][:200000])
    if isinstance(r, dict) and r.get("structuredContent"):
        print(json.dumps(r["structuredContent"])[:200000])
    if "error" in res:
        print("ERROR", json.dumps(res["error"])[:3000])

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "toolsets":
        show(tool("list_toolsets", {}))
    elif cmd == "describe":
        show(tool("describe_toolset", {"toolset_name": sys.argv[2]}))
    elif cmd == "call":
        show(tool("call_tool", {"toolset_name": sys.argv[2], "tool_name": sys.argv[3], "arguments": json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}}))
    elif cmd == "py":
        code = open(sys.argv[2], encoding="utf-8").read()
        show(tool("call_tool", {"toolset_name": "editor_toolset.toolsets.programmatic.ProgrammaticToolset",
                                "tool_name": "execute_tool_script", "arguments": {"script": code}}))
