"""Valida un CSV de tabla contra su .schema.json antes de importar.

Uso: python validate_rows.py DT_Items.csv DT_Items.schema.json [--refs DT_Other.csv ...]
Revisa: columnas, tipos, rangos (min/max), RowName único y no vacío, valores permitidos
("allowed": [...]) y referencias cruzadas ("ref": "DT_Other.Col" o "DT_Other.RowName").
Imprime KIT_PROBLEM por cada problema y KIT_FAIL o KIT_OK. Salida 1 si falla.
"""
import argparse
import csv
import json
import os
import sys


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        data = list(csv.reader(f))
    return data[0], data[1:]


def validate(header, rows, schema, ref_tables=None):
    """ref_tables: {nombre_tabla: (header, rows)}. Devuelve lista de problemas (texto)."""
    ref_tables = ref_tables or {}
    cols, probs = schema["columns"], []
    if len(header) != len(cols):
        return ["columnas: el CSV tiene %d y el esquema %d" % (len(header), len(cols))]
    for j, c in enumerate(cols):
        if j > 0 and header[j] != c["name"]:
            probs.append("encabezado %d: '%s' != '%s'" % (j, header[j], c["name"]))
    seen = set()
    for n, r in enumerate(rows, start=2):  # línea 2 = primera fila de datos
        if len(r) != len(cols):
            probs.append("linea %d: %d celdas, se esperaban %d" % (n, len(r), len(cols)))
            continue
        if r[0] == "":
            probs.append("linea %d: RowName vacio" % n)
        elif r[0] in seen:
            probs.append("linea %d: RowName repetido '%s'" % (n, r[0]))
        seen.add(r[0])
        for j, c in enumerate(cols):
            v, t, where = r[j], c["type"], "linea %d col %s" % (n, c["name"])
            if v == "":
                if c.get("required") and j > 0:
                    probs.append(where + ": vacio y requerido")
                continue
            if t in ("int", "float"):
                try:
                    x = int(v) if t == "int" else float(v)
                except ValueError:
                    probs.append("%s: '%s' no es %s" % (where, v, t))
                    continue
                if "min" in c and x < c["min"]:
                    probs.append("%s: %s < min %s" % (where, v, c["min"]))
                if "max" in c and x > c["max"]:
                    probs.append("%s: %s > max %s" % (where, v, c["max"]))
            elif t == "bool" and v.lower() not in ("true", "false", "0", "1"):
                probs.append("%s: '%s' no es bool" % (where, v))
            if "allowed" in c and v not in c["allowed"]:
                probs.append("%s: '%s' fuera de %s" % (where, v, c["allowed"]))
            if "ref" in c:
                tname, _, col = c["ref"].partition(".")
                if tname not in ref_tables:
                    probs.append("%s: tabla de referencia '%s' no cargada" % (where, tname))
                else:
                    h, rr = ref_tables[tname]
                    if col in ("", "RowName", "Name"):
                        k = 0
                    elif col in h:
                        k = h.index(col)
                    else:
                        probs.append("%s: ref a columna inexistente '%s'" % (where, c["ref"]))
                        continue
                    if v not in {x[k] for x in rr}:
                        probs.append("%s: '%s' no existe en %s" % (where, v, c["ref"]))
    return probs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("schema")
    ap.add_argument("--refs", nargs="*", default=[], help="CSV referenciados (nombre de tabla = archivo sin .csv)")
    a = ap.parse_args(argv)
    with open(a.schema, encoding="utf-8") as f:
        schema = json.load(f)
    header, rows = read_csv(a.csv)
    refs = {os.path.splitext(os.path.basename(p))[0]: read_csv(p) for p in a.refs}
    probs = validate(header, rows, schema, refs)
    for p in probs:
        print("KIT_PROBLEM", p)
    print(("KIT_FAIL %d problemas" % len(probs)) if probs else "KIT_OK")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
