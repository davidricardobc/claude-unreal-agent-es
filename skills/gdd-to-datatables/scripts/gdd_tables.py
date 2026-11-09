"""Tablas de un GDD (markdown o CSV) a CSV UTF-8 con BOM, esquema inferido y etiquetas.

Uso:
  python gdd_tables.py gdd.md --out Content/Data/Source        # un CSV + .schema.json por tabla
  python gdd_tables.py items.csv --out Content/Data/Source
  python gdd_tables.py gdd.md --list                           # solo muestra las tablas halladas
Solo biblioteca estándar. La primera columna es el nombre de fila (RowName).
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import unicodedata


def slugify(text, sep="_"):
    """Texto libre a clave ASCII estable: 'Alas Rápidas!' -> 'Alas_Rapidas'."""
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", sep, t).strip(sep)
    if not t:
        return "X"
    return ("_" + t) if t[0].isdigit() and sep == "_" else t


def _cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def parse_markdown_tables(text):
    """Devuelve [(título, encabezados, filas)]. El título es el último encabezado '#' previo."""
    tables, title, lines, i = [], "table", text.splitlines(), 0
    while i < len(lines):
        m = re.match(r"^\s*#{1,6}\s+(.*)", lines[i])
        if m:
            title = m.group(1).strip()
        if lines[i].count("|") >= 1 and i + 1 < len(lines) and SEP_RE.match(lines[i + 1]):
            header = _cells(lines[i])
            rows, i = [], i + 2
            while i < len(lines) and lines[i].count("|") >= 1:
                r = _cells(lines[i])
                rows.append((r + [""] * len(header))[:len(header)])
                i += 1
            tables.append((title, header, rows))
            continue
        i += 1
    return tables


def parse_csv_text(text, title="table"):
    text = text.lstrip("﻿")
    data = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not data:
        return []
    n = len(data[0])
    return [(title, [c.strip() for c in data[0]], [([c.strip() for c in r] + [""] * n)[:n] for r in data[1:]])]


def load_tables(path):
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    if path.lower().endswith(".csv"):
        return parse_csv_text(text, os.path.splitext(os.path.basename(path))[0])
    return parse_markdown_tables(text)


# Ronda 8 (TableFlyer): un GDD escrito por personas dice yes/no o si/no; UE solo acepta true/false en el CSV.
BOOL_WORDS = {"true": "true", "false": "false", "yes": "true", "no": "false", "si": "true", "s\u00ed": "true"}


def _is_int(v):
    return re.fullmatch(r"[+-]?\d+", v) is not None


def _is_float(v):
    return re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", v) is not None


def infer_type(values):
    vals = [v for v in values if v != ""]
    if not vals:
        return "string"
    if all(v.lower() in BOOL_WORDS for v in vals):
        return "bool"
    if all(_is_int(v) for v in vals):
        return "int"
    if all(_is_float(v.replace(",", ".")) for v in vals):
        return "float"
    return "string"


def normalize_header(h):
    """Encabezado a identificador válido de C++/UE: 'Daño (dps)' -> 'Dano_dps'."""
    s = slugify(h)
    return s[0].upper() + s[1:]


def pascal(text):
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", slugify(text, " ")) if w)


def normalize_table(title, header, rows, warnings=None, prefix=""):
    """Aplica claves ASCII y devuelve (cols, filas_normalizadas, esquema).

    Agrega la columna DisplayName (text) con el valor original de la primera columna.
    Lanza ValueError si dos encabezados normalizan igual (la USTRUCT no compilaría).
    warnings: lista opcional donde se anotan avisos (ej. separador de miles).
    """
    cols = [normalize_header(h) for h in header]
    dups = sorted({c for c in cols if cols.count(c) > 1})
    if dups:
        raise ValueError("encabezados repetidos tras normalizar: %s" % ", ".join(dups))
    if "DisplayName" in cols:
        raise ValueError("la columna DisplayName esta reservada para el texto original")
    n = len(cols)
    out = []
    for r in rows:
        r = (list(r) + [""] * n)[:n]
        display = r[0]
        r[0] = slugify(r[0])  # RowName estable
        for j in range(1, n):
            if re.fullmatch(r"[+-]?\d{1,3},\d{3}", r[j]) and warnings is not None:
                warnings.append("fila %s col %s: '%s' se leyo como decimal (%s); si era miles, corregir" % (
                    r[0], cols[j], r[j], r[j].replace(",", ".")))
            if "," in r[j] and _is_float(r[j].replace(",", ".")):
                r[j] = r[j].replace(",", ".")  # coma decimal a punto
        r.append(display)
        out.append(r)
    cols = cols + ["DisplayName"]
    base = pascal(title) or "Table"
    schema = {"struct": "F" + prefix + base + "Row", "table": "DT_" + base, "columns": []}
    for j, c in enumerate(cols):
        t = "name" if j == 0 else "text" if c == "DisplayName" else infer_type([r[j] for r in out])
        schema["columns"].append({"name": c, "type": t, **({"unique": True} if j == 0 else {})})
        if t == "bool":
            for r in out:
                if r[j] != "":
                    r[j] = BOOL_WORDS[r[j].lower()]
    return cols, out, schema


def write_csv(path, cols, rows):
    """UTF-8 con BOM, fin de línea LF. Primera columna 'Name' (verificado en 5.8.4: la importación con ese nombre funciona)."""
    cols = ["Name"] + list(cols[1:])
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        w.writerows(rows)


def suggest_tags(rows, prefix, col=0):
    """Una etiqueta por fila: 'Prefix.RowName'. Lista ordenada sin repetir."""
    return sorted({prefix.rstrip(".") + "." + slugify(r[col]) for r in rows})


def tags_ini_lines(tags):
    """Formato de DefaultGameplayTags.ini (sin verificar en 5.8): sección más una línea por etiqueta."""
    return ["[/Script/GameplayTags.GameplayTagsSettings]"] + ['+GameplayTagList=(Tag="%s",DevComment="")' % t for t in tags]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", default="Content/Data/Source")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--tag-prefix", help="escribe <tabla>.tags.txt y .tags.ini con etiquetas sugeridas")
    ap.add_argument("--struct-prefix", default="", help="prefijo del struct (TF -> FTFPlanesRow) para no chocar con otros modulos")
    a = ap.parse_args(argv)
    tables = load_tables(a.source)
    if not tables:
        print("KIT_FAIL sin tablas en", a.source)
        return 1
    for title, header, rows in tables:
        warns = []
        try:
            cols, nrows, schema = normalize_table(title, header, rows, warns, a.struct_prefix)
        except ValueError as e:
            print("KIT_FAIL tabla '%s': %s" % (title, e))
            return 1
        for w in warns:
            print("KIT_WARN", w)
        print("KIT_INFO tabla '%s': %d filas, %d columnas -> %s" % (title, len(nrows), len(cols), schema["table"]))
        if a.list:
            continue
        os.makedirs(a.out, exist_ok=True)
        base = os.path.join(a.out, schema["table"])
        write_csv(base + ".csv", cols, nrows)
        with open(base + ".schema.json", "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        if a.tag_prefix:
            tags = suggest_tags(nrows, a.tag_prefix)
            with open(base + ".tags.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(tags) + "\n")
            with open(base + ".tags.ini", "w", encoding="utf-8") as f:
                f.write("\n".join(tags_ini_lines(tags)) + "\n")
    print("KIT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
