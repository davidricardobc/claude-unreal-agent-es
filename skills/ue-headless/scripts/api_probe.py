"""Sonda de API compartida del kit: lee los api.txt de las skills y revisa cada entrada en `unreal`.

Formato de cada línea de api.txt (comentarios con #):
  Clase                     la clase o el enum existe
  función                   atributo del módulo unreal (sin punto), por ejemplo register_slate_post_tick_callback
  Clase.miembro             el miembro existe (no se revisa el tipo)
  Clase.miembro func        el miembro existe Y se llama con () (UFUNCTION)
  Clase.miembro prop        el miembro existe Y es propiedad: se usa con get/set_editor_property, sin ()

Por qué distingue func de prop: en build-tile el código llamaba comp.is_component_partitioned()
cuando en 5.8 es la UPROPERTY bIsComponentPartitioned. hasattr dio True y el error salió en vivo.

Uso:
  Dentro de UE (con ue-headless/run-python.ps1):
    KIT_API_SKILLS=asset-intake,build-tile  (opcional; vacío = todas)
    run-python.ps1 ... -Script .claude/skills/ue-headless/scripts/api_probe.py
  Fuera de UE: python api_probe.py [--skills a,b]  -> valida el formato y sale con KIT_PROBE_SKIP.
Imprime OK / FALTA / TIPO por línea y KIT_OK si nada falla.
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.normpath(os.path.join(HERE, "..", ".."))
KINDS = ("func", "prop")


def parse_line(line):
    """Devuelve (clase_o_None, miembro_o_None, nombre, tipo_o_None) o None si es comentario/vacía."""
    line = line.split("#", 1)[0].strip()
    if not line:
        return None
    parts = line.split()
    if len(parts) > 2 or (len(parts) == 2 and parts[1] not in KINDS):
        raise ValueError("formato 'Clase.miembro [func|prop]': " + line)
    name, kind = parts[0], (parts[1] if len(parts) == 2 else None)
    dots = name.count(".")
    if dots > 1:
        raise ValueError("un solo punto (Clase.miembro): " + line)
    if dots == 0:
        if kind:
            raise ValueError("func/prop solo con Clase.miembro: " + line)
        return (None, None, name, None)
    cls, member = name.split(".")
    if not cls or not member:
        raise ValueError("Clase.miembro incompleto: " + line)
    return (cls, member, name, kind)


def read_entries(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            e = parse_line(line)
            if e:
                out.append(e)
    return out


def find_api_files(skills_dir=SKILLS_DIR, only=None):
    """api.txt de cada skill (en la raíz de la skill o en scripts/). only = lista de nombres."""
    files = sorted(glob.glob(os.path.join(skills_dir, "*", "api.txt")) +
                   glob.glob(os.path.join(skills_dir, "*", "scripts", "api.txt")))
    if only:
        want = set(only)
        files = [f for f in files if os.path.relpath(f, skills_dir).split(os.sep)[0] in want]
    return files


def kind_of(value):
    """func si se puede llamar, prop si no. En UE las UFUNCTION son callables y las
    UPROPERTY expuestas aparecen en la clase como descriptor no callable."""
    return "func" if callable(value) else "prop"


def has_editor_property(cls, member):
    """Respaldo para propiedades no expuestas como atributo: probar get_editor_property
    sobre el objeto por defecto (UObject) o una instancia vacía (struct)."""
    for make in (lambda: cls.get_default_object(), lambda: cls()):
        try:
            obj = make()
            obj.get_editor_property(member)
            return True
        except Exception:
            continue
    return False


def check(module, entry):
    """Devuelve (estado, detalle). estado: OK | FALTA | TIPO."""
    cls_name, member, name, kind = entry
    if cls_name is None:
        return ("OK", "") if hasattr(module, name) else ("FALTA", "")
    cls = getattr(module, cls_name, None)
    if cls is None:
        return ("FALTA", "no existe la clase")
    if hasattr(cls, member):
        found = kind_of(getattr(cls, member))
    elif has_editor_property(cls, member):
        found = "prop"
    else:
        return ("FALTA", "")
    if kind and kind != found:
        hint = "usar get/set_editor_property, sin ()" if found == "prop" else "llamarlo con ()"
        return ("TIPO", "api.txt dice %s pero es %s: %s" % (kind, found, hint))
    return ("OK", found if kind is None else "")


def main(argv):
    only = None
    env = os.environ.get("KIT_API_SKILLS", "").strip()
    if "--skills" in argv:
        env = argv[argv.index("--skills") + 1]
    if env:
        only = [s.strip() for s in env.split(",") if s.strip()]
    files = find_api_files(only=only)
    if not files:
        print("KIT_FAIL no hay api.txt para " + (env or "ninguna skill"))
        return False
    entries = []
    for f in files:
        skill = os.path.relpath(f, SKILLS_DIR).split(os.sep)[0]
        entries += [(skill, e) for e in read_entries(f)]
    try:
        import unreal
    except ImportError:
        print("KIT_PROBE_SKIP %d entradas en %d api.txt, formato OK, fuera de UE" % (len(entries), len(files)))
        return True
    bad = 0
    for skill, e in entries:
        state, detail = check(unreal, e)
        bad += state != "OK"
        print("%-5s %s: %s%s%s" % (state, skill, e[2], " " + e[3] if e[3] else "", "  (" + detail + ")" if detail else ""))
    print("KIT_OK" if not bad else "KIT_FAIL %d con problema" % bad)
    return not bad


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv) else 1)
