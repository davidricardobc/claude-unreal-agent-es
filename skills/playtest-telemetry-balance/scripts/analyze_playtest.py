"""Resume CSV de telemetría de playtests y escribe propuestas de balance en markdown.

Uso:
  python analyze_playtest.py <carpeta_o_csv>... --out docs/playtests/2026-01-01.md [--min-n 5] [--z 2.0]
Formato de entrada (una fila por evento, encabezado obligatorio):
  ts,session,build,round,player_id,event,subject,value
  ts = segundos desde el inicio de la sesión; event = spawn|death|kill|damage|use|round_end|<libre>;
  subject = arma, pieza, objeto o causa (ej. 'sword', 'storm'); value = número (daño, 1/0 de victoria, etc.).
Eventos que entiende: death (subject = causa), damage (value = daño), use (conteo por subject),
round_end (subject = loadout/pieza, value = 1 gana / 0 pierde).
Solo biblioteca estándar. NUNCA toca tablas: solo escribe propuestas para que un humano las apruebe.
"""
import argparse
import csv
import glob
import os
import statistics as st
import sys
from collections import defaultdict

FIELDS = ["ts", "session", "build", "round", "player_id", "event", "subject", "value"]


def load_events(paths):
    files = []
    for p in paths:
        files += sorted(glob.glob(os.path.join(p, "*.csv"))) if os.path.isdir(p) else [p]
    ev = []
    for fp in files:
        with open(fp, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if not all(k in r for k in FIELDS):
                    raise ValueError("%s: faltan columnas %s" % (fp, [k for k in FIELDS if k not in r]))
                try:
                    r["ts"] = float(r["ts"])
                except ValueError:
                    continue
                try:
                    r["value"] = float(r["value"]) if r["value"] != "" else 0.0
                except ValueError:
                    r["value"] = 0.0
                ev.append(r)
    return ev, files


def outliers(values, z=2.0):
    """Claves cuyo valor se aleja de la mediana más de z desviaciones robustas. Puro.

    Escala = 1.4826 * MAD. Si MAD es 0 (muchos valores iguales) se usa la desviación absoluta
    media * 1.2533; si también es 0, todo es igual y no hay outliers.
    """
    if len(values) < 3:
        return {}
    med = st.median(values.values())
    devs = [abs(v - med) for v in values.values()]
    scale = 1.4826 * st.median(devs)
    if scale == 0:
        scale = 1.2533 * (sum(devs) / len(devs))
    if scale == 0:
        return {}
    return {k: round((v - med) / scale, 2) for k, v in values.items() if abs(v - med) / scale >= z}


def win_rate_outliers(win_rate, wins_total, games_total, z=2.0, min_n=5):
    """Prueba binomial por subject contra la tasa global (sirve con 2 loadouts). Puro.

    win_rate: {subject: {"rate": p, "n": n}}. p0 = tasa global acotada a [0.05, 0.95].
    """
    if games_total <= 0:
        return {}
    p0 = min(max(wins_total / games_total, 0.05), 0.95)
    out = {}
    for k, v in win_rate.items():
        if v["n"] < min_n:
            continue
        zv = (v["rate"] - p0) / ((p0 * (1 - p0) / v["n"]) ** 0.5)
        if abs(zv) >= z:
            out[k] = round(zv, 2)
    return out


def summarize(ev, z=2.0, min_n=5):
    S = {"sessions": sorted({e["session"] for e in ev}), "builds": sorted({e["build"] for e in ev})}
    dur = defaultdict(float)
    for e in ev:
        dur[e["session"]] = max(dur[e["session"]], e["ts"])
    S["session_minutes"] = {k: round(v / 60, 2) for k, v in dur.items()}
    deaths = [e for e in ev if e["event"] == "death"]
    S["deaths_total"] = len(deaths)
    S["deaths_by_cause"] = dict(sorted(_count(deaths, "subject").items(), key=lambda x: -x[1]))
    start = {}  # inicio de cada ronda = primer evento de esa (sesión, ronda)
    for e in ev:
        k = (e["session"], e["round"])
        start[k] = min(start.get(k, e["ts"]), e["ts"])
    first = {}
    for e in sorted(deaths, key=lambda x: x["ts"]):
        k = (e["session"], e["round"])
        first.setdefault(k, e["ts"] - start[k])
    S["time_to_first_death_s"] = {"median": round(st.median(first.values()), 1) if first else None, "n": len(first)}
    uses = _count([e for e in ev if e["event"] == "use"], "subject")
    S["use_by_subject"] = dict(sorted(uses.items(), key=lambda x: -x[1]))
    mins = max(sum(dur.values()) / 60, 1e-9)
    dmg = defaultdict(float)
    for e in ev:
        if e["event"] == "damage":
            dmg[e["subject"]] += e["value"]
    S["damage_per_min"] = {k: round(v / mins, 2) for k, v in sorted(dmg.items(), key=lambda x: -x[1])}
    wins, games = defaultdict(float), defaultdict(int)
    for e in ev:
        if e["event"] == "round_end":
            games[e["subject"]] += 1
            wins[e["subject"]] += 1 if e["value"] >= 1 else 0
    S["win_rate"] = {k: {"rate": round(wins[k] / games[k], 3), "n": games[k]} for k in games}
    S["outliers"] = {
        "use": outliers({k: v for k, v in uses.items()}, z),
        "damage_per_min": outliers(S["damage_per_min"], z),
        "win_rate": win_rate_outliers(S["win_rate"], sum(wins.values()), sum(games.values()), z, min_n),
    }
    # Ronda 8 (TableFlyer): por loadout = subject del último "spawn" de la sesión. Así un juego sin rondas ni
    # victorias (arcade) igual compara aviones, armas o personajes por minuto jugado.
    cur, last_ts, per = {}, {}, defaultdict(lambda: defaultdict(float))
    for e in sorted(ev, key=lambda x: (x["session"], x["ts"])):
        sess = e["session"]
        if sess in cur:
            per[cur[sess]]["_min"] += (e["ts"] - last_ts[sess]) / 60.0
        last_ts[sess] = e["ts"]
        if e["event"] == "spawn":
            cur[sess] = e["subject"]
            continue
        if sess in cur and e["event"] in ("use", "damage", "death", "kill"):
            per[cur[sess]][e["event"]] += 1
    S["by_loadout"] = {k: {"min": round(v["_min"], 2),
                           **{ev_: round(v[ev_] / max(v["_min"], 1e-9), 2) for ev_ in ("use", "damage", "death", "kill")}}
                       for k, v in per.items() if v["_min"] > 0}
    # Eventos propios del juego (no estándar): conteo y media de value, para no perderlos en el resumen.
    known = {"spawn", "death", "kill", "damage", "use", "round_end", "session_end"}
    other = defaultdict(list)
    for e in ev:
        if e["event"] not in known:
            other[e["event"]].append(e["value"])
    S["other_events"] = {k: {"n": len(v), "mean": round(st.mean(v), 3)} for k, v in sorted(other.items())}
    S["min_n"] = min_n
    return S


def _count(rows, key):
    c = defaultdict(int)
    for r in rows:
        c[r[key]] += 1
    return c


def propose(S):
    """Lista de propuestas. Cada una: subject, signal, suggestion. Heurísticas simples; el humano decide."""
    out = []
    for k, zv in S["outliers"]["win_rate"].items():
        n = S["win_rate"][k]["n"]
        out.append((k, "tasa de victoria atipica (z=%s, n=%d)" % (zv, n),
                    "bajar su potencia 5-10%" if zv > 0 else "subir su potencia 5-10%"))
    for k, zv in S["outliers"]["damage_per_min"].items():
        out.append((k, "dano por minuto atipico (z=%s)" % zv,
                    "reducir dano o cadencia 10%" if zv > 0 else "revisar si es usable; subir dano 10%"))
    for k, zv in S["outliers"]["use"].items():
        out.append((k, "uso atipico (z=%s)" % zv,
                    "alto uso: revisar si domina (costo/peso)" if zv > 0 else "bajo uso: revisar visibilidad o utilidad"))
    return out


def render(S, props, files):
    L = ["# Resumen de playtest", "", "Estado: BORRADOR. Ningun cambio se aplica sin aprobacion humana.", "",
         "- Archivos: %d. Sesiones: %d. Builds: %s" % (len(files), len(S["sessions"]), ", ".join(S["builds"]) or "-"),
         "- Muertes: %d. Primera muerte (mediana): %s s (n=%d)" % (
             S["deaths_total"], S["time_to_first_death_s"]["median"], S["time_to_first_death_s"]["n"]),
         "- Duracion por sesion (min): " + ", ".join("%s=%s" % kv for kv in S["session_minutes"].items()), ""]
    for title, key in (("Muertes por causa", "deaths_by_cause"), ("Uso por arma o pieza", "use_by_subject"),
                       ("Dano por minuto", "damage_per_min")):
        L += ["## " + title, "", "| subject | valor |", "|---|---|"]
        L += ["| %s | %s |" % kv for kv in S[key].items()] or ["| - | - |"]
        L.append("")
    L += ["## Por loadout (ultimo spawn de la sesion), eventos por minuto", "",
          "| loadout | minutos | use/min | damage/min | death/min | kill/min |", "|---|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %s | %s | %s |" % (k, v["min"], v["use"], v["damage"], v["death"], v["kill"])
          for k, v in S.get("by_loadout", {}).items()] or ["| - | - | - | - | - | - |"]
    L += ["", "## Otros eventos del juego", "", "| evento | n | media de value |", "|---|---|---|"]
    L += ["| %s | %d | %s |" % (k, v["n"], v["mean"]) for k, v in S.get("other_events", {}).items()] or ["| - | - | - |"]
    L.append("")
    L += ["## Tasa de victoria", "", "round_end: value 1 = gana, 0 = pierde (otro uso del campo da tasas sin sentido).", "",
          "| subject | tasa | n |", "|---|---|---|"]
    L += ["| %s | %s | %d |" % (k, v["rate"], v["n"]) for k, v in S["win_rate"].items()] or ["| - | - | - |"]
    L += ["", "## Propuestas de balance (pendientes de aprobar)", "",
          "Muestras chicas (n < %d) no generan propuesta de victoria. Una sesion no basta: repetir antes de decidir." % S["min_n"],
          "", "| # | subject | senal | propuesta | tabla/columna | aprobada |", "|---|---|---|---|---|---|"]
    L += ["| %d | %s | %s | %s | (completar) | [ ] |" % (i, a, b, c) for i, (a, b, c) in enumerate(props, 1)] or [
        "| - | - | sin outliers | - | - | - |"]
    L += ["", "Tras aprobar: editar el CSV fuente, validar, importar (skill gdd-to-datatables) y volver a jugar."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", default="docs/playtests/summary.md")
    ap.add_argument("--min-n", type=int, default=5)
    ap.add_argument("--z", type=float, default=2.0)
    a = ap.parse_args(argv)
    ev, files = load_events(a.inputs)
    if not ev:
        print("KIT_FAIL sin eventos")
        return 1
    S = summarize(ev, a.z, a.min_n)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(render(S, propose(S), files))
    print("KIT_INFO eventos: %d, archivos: %d -> %s" % (len(ev), len(files), a.out))
    print("KIT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
