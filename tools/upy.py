"""Ejecuta Python dentro del editor de Unreal abierto (la ejecución remota de PythonScriptPlugin debe estar activa).
Uso: python upy.py archivo.py [args...]   o   python upy.py -c "print(1)"
El script corre con sys.argv = [archivo, args...]. La salida (print/log) se devuelve en pantalla.
Raíz del motor desde la variable de entorno UE_ROOT (por defecto: la carpeta de instalación estándar de 5.8).
Consejo: escribir los scripts en un archivo (nunca un heredoc de shell) y usar barras / en las rutas.
"""
import sys, os, time

UE_ROOT = os.environ.get("UE_ROOT", "C:/Program Files/Epic Games/UE_5.8")
sys.path.insert(0, os.path.join(UE_ROOT, "Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python"))
import remote_execution as re_


def run(code, timeout=600):
    rex = re_.RemoteExecution()
    rex.start()
    try:
        t0 = time.time()
        while not rex.remote_nodes and time.time() - t0 < 15:
            time.sleep(0.2)
        if not rex.remote_nodes:
            print("NO EDITOR NODE FOUND (is bRemoteExecution on and the editor open?)")
            return 2
        rex.open_command_connection(rex.remote_nodes[0]["node_id"])
        res = rex.run_command(code, unattended=True, exec_mode=re_.MODE_EXEC_FILE)
        for o in res.get("output", []):
            print(o.get("output", "").rstrip())
        if not res.get("success"):
            print("FAILED:", res.get("result"))
            return 1
        return 0
    finally:
        rex.stop()


if __name__ == "__main__":
    if sys.argv[1] == "-c":
        code = sys.argv[2]
    else:
        path = os.path.abspath(sys.argv[1])
        args = [path] + sys.argv[2:]
        code = "import sys; sys.argv=%r; exec(compile(open(%r, encoding='utf-8').read(), %r, 'exec'), {'__name__':'__main__'})" % (args, path, path)
    sys.exit(run(code))
