"""Prueba de las funciones puras con datos ficticios. Correr: python tests/test_gdd.py"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import gdd_tables as g  # noqa: E402
import gen_ustruct  # noqa: E402
import validate_rows as v  # noqa: E402

MD = """# Armas
| ID | Daño | Cadencia (s) | Tipo |
|---|---|---|---|
| Rifle Ligero | 12 | 0,5 | auto |
| Escopeta | 40 | 1.2 | pump |

## Municion
| Arma | Cantidad |
|---|---|
| Rifle Ligero | 30 |
| Lanza Cohetes | 4 |
"""

tables = g.parse_markdown_tables(MD)
assert len(tables) == 2 and tables[0][0] == "Armas"
cols, rows, schema = g.normalize_table(*tables[0])
assert cols == ["ID", "Dano", "Cadencia_s", "Tipo", "DisplayName"], cols
assert rows[0][-1] == "Rifle Ligero"  # el texto original se conserva (I2)
assert rows[0][0] == "Rifle_Ligero" and rows[0][2] == "0.5"
assert [c["type"] for c in schema["columns"]] == ["name", "int", "float", "string", "text"]
assert schema["struct"] == "FArmasRow" and schema["table"] == "DT_Armas"

with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "a.csv")
    g.write_csv(p, cols, rows)
    raw = open(p, "rb").read()
    assert raw.startswith(b"\xef\xbb\xbf") and b"Name,Dano" in raw
    h, r = v.read_csv(p)
    assert v.validate(h, r, schema) == []

schema["columns"][1]["max"] = 20
probs = v.validate(["Name"] + cols[1:], rows, schema)
assert len(probs) == 1 and "> max" in probs[0], probs

dup = rows + [list(rows[0])]
assert any("repetido" in x for x in v.validate(["Name"] + cols[1:], dup, schema))

# referencia cruzada: Municion.Arma debe existir en DT_Armas
c2, r2, s2 = g.normalize_table(*tables[1])
s2["columns"][0]["ref"] = "DT_Armas.RowName"
refs = {"DT_Armas": (["Name"] + cols[1:], rows)}
probs = v.validate(["Name"] + c2[1:], r2, s2, refs)
assert len(probs) == 1 and "Lanza_Cohetes" in probs[0], probs

schema["columns"][1]["min"] = 0
hdr = gen_ustruct.render(schema, "MYMOD_API")
assert "struct MYMOD_API FArmasRow : public FTableRowBase" in hdr and "int32 Dano = 0;" in hdr
assert 'ClampMax="20"' in hdr and "Armas Row" not in hdr

tags = g.suggest_tags(rows, "Weapon.")
assert tags == ["Weapon.Escopeta", "Weapon.Rifle_Ligero"], tags
assert g.tags_ini_lines(tags[:1])[1].startswith("+GameplayTagList=")

# I3: fila CSV corta no revienta
t = g.parse_csv_text("ID,A,B\nx,1,2\ny,3\n", "T")[0]
assert t[2][1] == ["y", "3", ""]
_, r3, _ = g.normalize_table(*t)
assert len(r3[1]) == 4

# I4: encabezados que normalizan igual
try:
    g.normalize_table("T", ["ID", "Daño", "Dano"], [["a", "1", "2"]])
    raise AssertionError("debio fallar")
except ValueError as e:
    assert "Dano" in str(e)

# P2: separador de miles avisa; .ini trae sección
w = []
g.normalize_table("T", ["ID", "V"], [["a", "1,000"]], w)
assert len(w) == 1 and "1.000" in w[0]
assert g.tags_ini_lines(["A.B"])[0] == "[/Script/GameplayTags.GameplayTagsSettings]"

# P1: ref a columna inexistente no lanza
s4 = {"columns": [{"name": "ID", "type": "name"}, {"name": "R", "type": "string", "ref": "DT_X.Nada"}]}
pr = v.validate(["Name", "R"], [["a", "z"]], s4, {"DT_X": (["Name", "C"], [["z", "1"]])})
assert len(pr) == 1 and "inexistente" in pr[0], pr
print("KIT_OK test_gdd")
