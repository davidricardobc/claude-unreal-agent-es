"""Vuelve a ejecutar OnConstruction de los actores listados en un archivo (un refPath por línea) con MCP set_properties."""
import json, sys, mcp
paths = open(sys.argv[1]).read().split()
prop = sys.argv[2] if len(sys.argv) > 2 else "bKeepMaterialColor"
val = json.loads(sys.argv[3]) if len(sys.argv) > 3 else False
code = "import json\ndef run():\n    n=0\n    for p in %r:\n        execute_tool('editor_toolset.toolsets.object.ObjectTools.set_properties', json.dumps({'instance':{'refPath':p},'values':json.dumps({%r:%r})}))\n        n+=1\n    return {'n':n}\n" % (paths, prop, val)
r = mcp.tool("call_tool", {"toolset_name": "editor_toolset.toolsets.programmatic.ProgrammaticToolset", "tool_name": "execute_tool_script", "arguments": {"script": code}})
print(json.dumps(r)[:300])
