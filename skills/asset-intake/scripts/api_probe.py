"""Sonda de API de asset-intake: atajo a la sonda compartida de ue-headless (distingue func de prop).

Dentro de UE (run-python.ps1): revisa solo el api.txt de esta skill; KIT_OK si nada falla.
Fuera de UE: valida el formato (KIT_PROBE_SKIP). Formato en ue-headless/scripts/api_probe.py.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.normpath(os.path.join(HERE, "..", "..", "ue-headless", "scripts", "api_probe.py"))


def _load_shared():
    # Carga por ruta con otro nombre: este archivo también se llama api_probe.
    import importlib.util
    spec = importlib.util.spec_from_file_location("ue_headless_api_probe", _SHARED)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shared = _load_shared()

SKILL = "asset-intake"


def read_entries(path=None):
    return shared.read_entries(path or os.path.join(HERE, "api.txt"))


if __name__ == "__main__":
    sys.exit(0 if shared.main(["api_probe.py", "--skills", SKILL]) else 1)
