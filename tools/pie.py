"""Ayudas de PIE para las pruebas de TableFlyer. Se importan desde los scripts de prueba:
   from pie import *  ->  start(), stop(), setp(obj, dict), getp(obj, names), xform(obj), shot(name)
Los objetos de PIE viven en /Game/Maps/UEDPIE_0_<Mapa>.<Mapa>:PersistentLevel.<Actor>_N
"""
import json, base64, time, os, mcp

MAP = os.environ.get("UE_PIE_MAP", "TableFlyerMap")
PIE = "/Game/Maps/UEDPIE_0_%s.%s:PersistentLevel." % (MAP, MAP)
CAPS = os.path.join(os.environ.get("UE_PROJECT_DIR", "."), "Saved", "Capturas") + os.sep


def call(ts, tool, args):
    r = mcp.tool("call_tool", {"toolset_name": ts, "tool_name": tool, "arguments": args})
    res = r.get("result", r)
    txt = ""
    for c in res.get("content", []) if isinstance(res, dict) else []:
        if c.get("type") == "text":
            txt = c["text"]
    try:
        return json.loads(txt).get("returnValue", json.loads(txt))
    except Exception:
        return txt


def start(warmup=2.0):
    return call("EditorToolset.EditorAppToolset", "StartPIE",
                {"options": {"playMode": "PlayMode_InViewPort", "warmupSeconds": warmup}})


def stop():
    return call("EditorToolset.EditorAppToolset", "StopPIE", {})


def setp(obj, values):
    return call("editor_toolset.toolsets.object.ObjectTools", "set_properties",
                {"instance": {"refPath": PIE + obj}, "values": json.dumps(values)})


def getp(obj, names):
    return call("editor_toolset.toolsets.object.ObjectTools", "get_properties",
                {"instance": {"refPath": PIE + obj}, "properties": names})


def xform(obj):
    return call("editor_toolset.toolsets.actor.ActorTools", "get_actor_transform", {"actor": {"refPath": PIE + obj}})


def set_xform(obj, loc, rot=None):
    x = {"location": {"x": loc[0], "y": loc[1], "z": loc[2]}}
    if rot:
        x["rotation"] = {"pitch": rot[0], "yaw": rot[1], "roll": rot[2]}
    return call("editor_toolset.toolsets.actor.ActorTools", "set_actor_transform", {"actor": {"refPath": PIE + obj}, "xform": x, "worldspace": True})


def shot(name):
    d = call("EditorToolset.EditorAppToolset", "CaptureEditorImage", {})
    try:
        img = d["data"] if "data" in d else d["image"]["data"]
    except Exception:
        print("CAPTURE FAIL", str(d)[:300])
        return None
    p = CAPS + name + ".png"
    open(p, "wb").write(base64.b64decode(img))
    return p
