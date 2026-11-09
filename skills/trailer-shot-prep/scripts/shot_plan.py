"""Plan de tomas de tráiler. Puro Python 3, sin Unreal (lo usan build_sequences.py y render-shots.ps1).

CSV de entrada (UTF-8): moment,duration_s,camera_type,map[,target][,notes]
  moment       nombre corto de la toma ("opening_dive")
  duration_s   segundos de la toma (>= 0.5)
  camera_type  static | orbit | dolly | crane
  map          ruta del mapa de Unreal ("/Game/Maps/DemoRange")
  target       (opcional) etiqueta del actor que se mira; si falta, el centro es 0,0,0
Uso:
  python shot_plan.py check shots.csv [--min-s 30 --max-s 60]     validar y mostrar la línea de tiempo
  python shot_plan.py manifest shots.csv out.csv --out-dir <dir>   manifest para render-shots.ps1
  python shot_plan.py ffmpeg shots.csv <frames_dir>               comandos de ensamblado
El rango de duración por defecto es 30 a 60 s (lo que piden muchos concursos); se cambia con --min-s y --max-s.
Última línea: SHOTPLAN_OK o SHOTPLAN_FAIL. Código de salida 0 o 1.
"""
import csv
import math
import os
import re
import sys

CAMERA_TYPES = ("static", "orbit", "dolly", "crane")
MIN_TOTAL_S, MAX_TOTAL_S = 30.0, 60.0
HOOK_S = 3.0
FPS = 60
SEQ_DIR = "/Game/Cine/Trailer"


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return s or "shot"


def load_shots(path):
    shots = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            try:
                dur = float(row.get("duration_s", ""))
            except ValueError:
                dur = float("nan")
            shots.append({
                "index": i,
                "moment": row.get("moment", ""),
                "duration_s": dur,
                "camera_type": row.get("camera_type", "").lower(),
                "map": row.get("map", ""),
                "target": row.get("target", ""),
                "notes": row.get("notes", ""),
            })
    for s in shots:
        s["seq_name"] = "LS_%02d_%s" % (s["index"], slug(s["moment"]))
        s["seq_path"] = "%s/%s" % (SEQ_DIR, s["seq_name"])
        s["frames"] = int(round(s["duration_s"] * FPS)) if math.isfinite(s["duration_s"]) else 0
    return shots


def validate(shots, min_s=MIN_TOTAL_S, max_s=MAX_TOTAL_S):
    """Devuelve (errores, avisos). min_s y max_s: el rango de duración total lo fija cada proyecto."""
    errs, warns = [], []
    if not shots:
        return ["sin tomas"], warns
    seen = set()
    for s in shots:
        tag = "toma %d (%s)" % (s["index"], s["moment"])
        if not s["moment"]:
            errs.append("toma %d: falta moment" % s["index"])
        if s["moment"] in seen:
            errs.append("%s: nombre repetido" % tag)
        seen.add(s["moment"])
        if not math.isfinite(s["duration_s"]) or s["duration_s"] < 0.5:
            errs.append("%s: duration_s inválida (mínimo 0,5)" % tag)
        if s["camera_type"] not in CAMERA_TYPES:
            errs.append("%s: camera_type '%s' no está en %s" % (tag, s["camera_type"], "/".join(CAMERA_TYPES)))
        if not s["map"].startswith("/"):
            errs.append("%s: map debe ser una ruta de Unreal tipo /Game/Maps/X" % tag)
    total = sum(s["duration_s"] for s in shots if math.isfinite(s["duration_s"]))
    if total < min_s:
        errs.append("duración total %.1f s: mínimo %.0f s" % (total, min_s))
    if total > max_s:
        errs.append("duración total %.1f s: máximo %.0f s" % (total, max_s))
    if shots[0]["duration_s"] > HOOK_S:
        warns.append("la primera toma dura %.1f s: el gancho debe ocurrir en los primeros %.0f s (corta antes o abre con acción)"
                     % (shots[0]["duration_s"], HOOK_S))
    if sum(1 for s in shots if s["duration_s"] > 8) > 2:
        warns.append("más de 2 tomas largas (> 8 s): un tráiler corto respira con cortes más rápidos")
    return errs, warns


def look_at(pos, target):
    """(pitch, yaw) en grados para mirar de pos a target. Convención Unreal: X adelante, Z arriba, yaw sobre Z."""
    dx, dy, dz = target[0] - pos[0], target[1] - pos[1], target[2] - pos[2]
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    return pitch, yaw


def camera_keys(camera_type, center, radius, duration_s, fps=FPS, height=None):
    """Lista de claves [{frame, loc:(x,y,z), rot:(pitch,roll,yaw)}] relativas a center. Unidades de Unreal (cm).
    radius: distancia de trabajo a la que cabe el sujeto. Cuatro tipos; la cámara siempre mira a center."""
    if camera_type not in CAMERA_TYPES:
        raise ValueError("camera_type desconocido: %s" % camera_type)
    n_frames = max(1, int(round(duration_s * fps)))
    h = radius * 0.3 if height is None else height
    cx, cy, cz = center

    def key(frame, x, y, z):
        p, yw = look_at((x, y, z), center)
        return {"frame": frame, "loc": (x, y, z), "rot": (p, 0.0, yw)}

    if camera_type == "static":
        return [key(0, cx - radius, cy, cz + h)]
    if camera_type == "orbit":
        steps = max(2, n_frames // 15)  # una clave cada ~0,25 s a 60 fps
        out = []
        for i in range(steps + 1):
            a = math.radians(-45.0 + 90.0 * i / steps)  # arco de 90 grados centrado detrás del sujeto
            out.append(key(int(round(n_frames * i / steps)), cx - radius * math.cos(a), cy + radius * math.sin(a), cz + h))
        return out
    if camera_type == "dolly":
        return [key(0, cx - radius * 1.6, cy, cz + h), key(n_frames, cx - radius * 0.7, cy, cz + h * 0.6)]
    # crane: sube y se acerca un poco
    return [key(0, cx - radius, cy, cz + h * 0.2), key(n_frames, cx - radius * 0.8, cy, cz + h * 3.0)]


def ffmpeg_commands(shots, frames_dir, fps=FPS, crf=14):
    """Comandos para pasar cada secuencia PNG a MP4 intermedio y unirlos. Sin verificar el patrón del nombre de archivo."""
    cmds, lst = [], []
    for s in shots:
        src = os.path.join(frames_dir, s["seq_name"] + ".%04d.png").replace("\\", "/")
        out = os.path.join(frames_dir, s["seq_name"] + ".mp4").replace("\\", "/")
        cmds.append('ffmpeg -y -framerate %d -i "%s" -c:v libx264 -crf %d -pix_fmt yuv420p "%s"' % (fps, src, crf, out))
        lst.append("file '%s'" % out)
    cmds.append("# crear concat.txt con:\n" + "\n".join(lst))
    cmds.append('ffmpeg -y -f concat -safe 0 -i concat.txt -c copy trailer_raw.mp4')
    return cmds


def write_manifest(shots, path, out_dir=""):
    """out_dir: carpeta de fotogramas. Debe ser la misma de KIT_TRAILER_OUT del preset; render-shots.ps1 la usa por defecto."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["index", "seq_name", "seq_path", "map", "duration_s", "frames", "camera_type", "out_dir"])
        for s in shots:
            w.writerow([s["index"], s["seq_name"], s["seq_path"], s["map"], s["duration_s"], s["frames"],
                        s["camera_type"], out_dir])


def timeline(shots):
    t, lines = 0.0, []
    for s in shots:
        lines.append("%5.1f - %5.1f  %-28s %-7s %s" % (t, t + s["duration_s"], s["seq_name"], s["camera_type"], s["map"]))
        t += s["duration_s"]
    lines.append("total %.1f s, %d fotogramas a %d fps" % (t, sum(s["frames"] for s in shots), FPS))
    return lines


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("check", "manifest", "ffmpeg"))
    ap.add_argument("csv")
    ap.add_argument("target", nargs="?", help="manifest: archivo de salida; ffmpeg: carpeta de fotogramas")
    ap.add_argument("--min-s", type=float, default=MIN_TOTAL_S, help="duración total mínima (por defecto 30)")
    ap.add_argument("--max-s", type=float, default=MAX_TOTAL_S, help="duración total máxima (por defecto 60)")
    ap.add_argument("--out-dir", default="", help="manifest: carpeta de fotogramas (igual a KIT_TRAILER_OUT)")
    a = ap.parse_args(argv)
    shots = load_shots(a.csv)
    errs, warns = validate(shots, a.min_s, a.max_s)
    print("\n".join(timeline(shots)))
    for w in warns:
        print("AVISO", w)
    for e in errs:
        print("ERROR", e)
    if errs:
        print("SHOTPLAN_FAIL")
        return 1
    if a.command in ("manifest", "ffmpeg") and not a.target:
        print("ERROR falta el argumento de salida")
        print("SHOTPLAN_FAIL")
        return 1
    if a.command == "manifest":
        write_manifest(shots, a.target, a.out_dir)
        print("manifest:", a.target)
    if a.command == "ffmpeg":
        print("\n".join(ffmpeg_commands(shots, a.target)))
    print("SHOTPLAN_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
