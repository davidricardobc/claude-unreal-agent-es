#!/usr/bin/env python3
"""Registro de licencias (CSV): validador y lista de assets de terceros. Python puro.

Uso:
  python license_registry.py validate assets-licenses.csv
  python license_registry.py checklist assets-licenses.csv [-o third-party-assets.md]
  python license_registry.py gitignore <repo_dir> <ruta_relativa> [...]   # exige que esté ignorada

Columnas obligatorias: asset, source, license, allowed_use, declare
Columnas opcionales: ai_generated (yes/no), reviewed (yes/no), uploaded_to_ai (yes/no),
  credit_text, url, notes
Salida del validador: ERROR/WARN por fila y VALID o INVALID (código 1 si hay ERROR).
Las reglas son un resumen del autor de los términos públicos de las licencias (Synty, Meshy, CC0);
comprobar los términos vigentes del proveedor. Reglas de un concurso o cliente concreto: revisar sus reglas oficiales aparte.
"""
import csv
import subprocess
import sys

REQUIRED = ["asset", "source", "license", "allowed_use", "declare"]
AI_SOURCES = ("meshy", "tripo", "hunyuan", "luma", "rodin", "sloyd")
BLOCKED_SOURCES = {"hunyuan": "Hunyuan3D-2: su licencia no aplica en UE, Reino Unido ni Corea del Sur"}
YESNO = ("yes", "no")


def is_yes(v):
    return (v or "").strip().lower() == "yes"


def read_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return r.fieldnames or [], list(r)


def validate_rows(fields, rows):
    issues = []
    for c in REQUIRED:
        if c not in fields:
            issues.append(("ERROR", 0, "falta la columna '%s'" % c))
    if issues:
        return issues
    seen = set()
    for n, r in enumerate(rows, start=2):  # la fila 1 es el encabezado
        asset = (r.get("asset") or "").strip()
        src = (r.get("source") or "").lower()

        def err(t):
            issues.append(("ERROR", n, "%s: %s" % (asset or "?", t)))

        def warn(t):
            issues.append(("WARN", n, "%s: %s" % (asset or "?", t)))

        if not asset:
            err("asset vacio")
            continue
        if asset in seen:
            err("asset repetido")
        seen.add(asset)
        for c in ("source", "license", "allowed_use"):
            if not (r.get(c) or "").strip():
                err("%s vacio" % c)
        for key, why in BLOCKED_SOURCES.items():
            if key in src:
                err("fuente bloqueada: " + why)
        d = (r.get("declare") or "").strip().lower()
        if d not in YESNO:
            err("declare debe ser yes o no")
        ai = is_yes(r.get("ai_generated")) or any(s in src for s in AI_SOURCES)
        if ai:
            if d != "yes":
                err("asset de IA 3D: declare debe ser yes")
            if not is_yes(r.get("reviewed")):
                err("asset de IA 3D sin revisar (topologia, escala, UV): reviewed=yes")
        if "synty" in src or "synty" in (r.get("license") or "").lower():
            if is_yes(r.get("uploaded_to_ai")):
                err("Synty no se sube a generadores 3D de IA")
            if "team" not in (r.get("allowed_use") or "").lower() and "equipo" not in (r.get("allowed_use") or "").lower():
                warn("Synty: allowed_use deberia decir que no sale del equipo")
            if d != "yes":
                warn("Synty: confirmar si hay que declararlo (concurso, tienda o cliente)")
        lic = (r.get("license") or "").lower()
        if ("cc by" in lic or "cc-by" in lic) and "cc0" not in lic and not (r.get("credit_text") or "").strip():
            err("licencia CC BY exige atribucion: falta credit_text")
        if (r.get("license") or "").strip().lower() in ("unknown", "desconocida", "?"):
            err("licencia desconocida: no usar hasta confirmarla")
    return issues


def checklist_markdown(rows):
    """Lista de assets de terceros: solo filas con declare=yes, por fuente."""
    groups = {}
    for r in rows:
        if is_yes(r.get("declare")):
            groups.setdefault((r.get("source") or "?").strip(), []).append(r)
    out = ["# Lista de assets de terceros", ""]
    if not groups:
        out.append("Ningun asset de terceros declarado.")
    for src in sorted(groups):
        out.append("## %s" % src)
        for r in sorted(groups[src], key=lambda x: x["asset"]):
            line = "- [ ] %s | licencia: %s" % (r["asset"].strip(), r["license"].strip())
            if (r.get("url") or "").strip():
                line += " | %s" % r["url"].strip()
            if (r.get("credit_text") or "").strip():
                line += ' | credito: "%s"' % r["credit_text"].strip()
            if is_yes(r.get("ai_generated")):
                line += " | generado con IA"
            out.append(line)
        out.append("")
    undeclared = [r["asset"] for r in rows if not is_yes(r.get("declare"))]
    out.append("Sin declarar (%d): confirmar que de verdad no hay que declararlos." % len(undeclared))
    return "\n".join(out) + "\n"


def check_gitignored(repo, paths):
    """Devuelve las rutas que git NO ignora (deberían estar en .gitignore)."""
    bad = []
    for p in paths:
        r = subprocess.run(["git", "-C", repo, "check-ignore", "-q", p])
        if r.returncode != 0:
            bad.append(p)
    return bad


def main(argv):
    if len(argv) < 2 or argv[0] not in ("validate", "checklist", "gitignore"):
        print(__doc__)
        return 2
    if argv[0] == "gitignore":
        if len(argv) < 3:
            print("uso: gitignore <repo_dir> <ruta> [...]")
            return 2
        bad = check_gitignored(argv[1], argv[2:])
        for p in bad:
            print("ERROR no esta en .gitignore: " + p)
        print("INVALID" if bad else "VALID")
        return 1 if bad else 0
    if "-o" in argv and argv.index("-o") + 1 >= len(argv):
        print("ERROR -o necesita una ruta de salida")
        return 2
    fields, rows = read_rows(argv[1])
    issues = validate_rows(fields, rows)
    for lvl, n, msg in issues:
        print("%s fila %d: %s" % (lvl, n, msg))
    bad = any(i[0] == "ERROR" for i in issues)
    if argv[0] == "validate":
        print("INVALID" if bad else "VALID")
        return 1 if bad else 0
    if bad:
        print("INVALID: corregir antes de generar la lista")
        return 1
    md = checklist_markdown(rows)
    if "-o" in argv:
        with open(argv[argv.index("-o") + 1], "w", encoding="utf-8") as f:
            f.write(md)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
