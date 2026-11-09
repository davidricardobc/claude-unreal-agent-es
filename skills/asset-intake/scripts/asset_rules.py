"""Reglas puras de entrada de assets (sin Unreal): nombres, carpetas y escala.

Se importa desde batch_import.py (dentro de UE) y desde los tests (fuera de UE).
Todo en cm, que es la unidad de UE.
"""
import re

PREFIXES = {
    "static_mesh": "SM_",
    "skeletal_mesh": "SK_",
    "material": "M_",
    "material_instance": "MI_",
    "texture": "T_",
}
TEXTURE_SUFFIXES = ("_D", "_N", "_ORM", "_E", "_M")  # color, normal, ORM, emisivo, máscara
NAME_RE = re.compile(r"^(SM|SK|M|MI|T)_[A-Z][A-Za-z0-9]*(_[A-Za-z0-9]+)*$")
FOLDER_ROOT = {"own": "/Game/Art", "third_party": "/Game/ThirdParty", "ai": "/Game/AI_Generated"}


def pascal(text):
    """'old wooden crate' o 'old-wooden_crate' -> 'OldWoodenCrate'."""
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", text) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def asset_name(kind, base, index=None):
    """asset_name('static_mesh', 'wood crate', 1) -> 'SM_WoodCrate_01'."""
    if kind not in PREFIXES:
        raise ValueError("tipo desconocido: %s" % kind)
    name = PREFIXES[kind] + pascal(base)
    if index is not None:
        name += "_%02d" % index
    return name


def validate_name(name, kind=None):
    """Devuelve lista de problemas (vacía si está bien)."""
    issues = []
    if not NAME_RE.match(name):
        issues.append("'%s' no sigue Prefijo_PascalCase" % name)
    if kind and not name.startswith(PREFIXES.get(kind, "?")):
        issues.append("'%s' deberia empezar con %s" % (name, PREFIXES.get(kind, "?")))
    if " " in name or any(ord(c) > 127 for c in name):
        issues.append("'%s' tiene espacios o tildes" % name)
    return issues


def target_folder(origin, category, pack=None):
    """target_folder('third_party', 'Props', 'Synty/PolygonFarm') -> '/Game/ThirdParty/Synty/PolygonFarm/Props'."""
    if origin not in FOLDER_ROOT:
        raise ValueError("origen desconocido: %s" % origin)
    parts = [FOLDER_ROOT[origin]]
    if pack:
        parts.append(pack.strip("/"))
    parts.append(pascal(category))
    return "/".join(parts)


def guess_scale(bbox_extent_cm, target_max_cm=None):
    """Factor de escala para una malla importada.

    bbox_extent_cm: (x, y, z) de la caja ya importada.
    target_max_cm: medida objetivo de la dimensión mayor. Si es None se adivina
    la unidad: una dimensión mayor menor de 5 casi seguro viene en metros (x100);
    mayor de 5000 casi seguro viene en mm (x0.1). Es una pista, confirmar siempre.
    Devuelve (factor, motivo).
    """
    biggest = max(bbox_extent_cm)
    if biggest <= 0:
        raise ValueError("caja vacia")
    if target_max_cm:
        return target_max_cm / biggest, "objetivo %s cm" % target_max_cm
    if biggest < 5:
        return 100.0, "parece metros"
    if biggest > 5000:
        return 0.1, "parece milimetros"
    return 1.0, "parece cm"


def pivot_offset(bbox_min_cm, bbox_max_cm, mode="bottom_center"):
    """Traslación que lleva el pivote al piso centrado (o al centro)."""
    cx = (bbox_min_cm[0] + bbox_max_cm[0]) / 2.0
    cy = (bbox_min_cm[1] + bbox_max_cm[1]) / 2.0
    cz = bbox_min_cm[2] if mode == "bottom_center" else (bbox_min_cm[2] + bbox_max_cm[2]) / 2.0
    return (-cx, -cy, -cz)


def plan_item(item, bbox_min, bbox_max):
    """Calcula nombre, carpeta, escala y pivote para un item del lote.

    item: dict con kind, base, origin, category, pack, index, target_max_cm.
    """
    extent = [b - a for a, b in zip(bbox_min, bbox_max)]
    scale, why = guess_scale(extent, item.get("target_max_cm"))
    name = asset_name(item.get("kind", "static_mesh"), item["base"], item.get("index"))
    return {
        "name": name,
        "folder": target_folder(item.get("origin", "own"), item.get("category", "Props"), item.get("pack")),
        "scale": scale,
        "scale_reason": why,
        "pivot_offset_cm": pivot_offset(bbox_min, bbox_max, item.get("pivot", "bottom_center")),
        "name_issues": validate_name(name, item.get("kind", "static_mesh")),
    }


def secondary_name(kind, original):
    """Renombra material/textura importados: 'wood_diffuse' + 'texture' -> 'T_WoodDiffuse'.
    Quita un prefijo previo (T_, Tex_, M_, MI_, Mat_) antes de aplicar el correcto."""
    if kind not in ("material", "material_instance", "texture"):
        raise ValueError("tipo desconocido: %s" % kind)
    stripped = re.sub(r"^(T|Tex|M|MI|Mat|Material)_", "", original)
    return PREFIXES[kind] + pascal(stripped)


def check_final_size(size_cm, target_max_cm, tol_cm=2.0):
    """Devuelve problema (str) si la dimensión mayor no llega al objetivo, o None."""
    if not target_max_cm:
        return None
    got = max(size_cm)
    if abs(got - target_max_cm) > tol_cm:
        return "medida final %.1f cm distinta del objetivo %s cm" % (got, target_max_cm)
    return None
