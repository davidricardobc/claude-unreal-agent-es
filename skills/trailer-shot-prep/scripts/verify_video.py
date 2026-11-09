"""Verifica resolución, fps y duración del video final con ffprobe. Puro Python 3 (usa ffprobe si está instalado).

Uso: python verify_video.py trailer.mp4 [--min-res 1920x1080] [--min-s 30] [--max-s 60]
Última línea: VIDEO_OK o VIDEO_FAIL. Salida: 0 ok, 1 falla, 3 sin ffprobe (no se pudo verificar; NO es un "pasó").
"""
import argparse
import json
import shutil
import subprocess
import sys


def probe(path):
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    r = subprocess.run([exe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "ffprobe falló")
    return json.loads(r.stdout)


def parse_rate(text):
    """'60000/1001' -> 59.94. 0 si no se puede."""
    try:
        a, b = text.split("/")
        return float(a) / float(b) if float(b) else 0.0
    except (ValueError, AttributeError):
        return 0.0


def evaluate(info, min_w=1920, min_h=1080, min_s=30.0, max_s=60.0):
    """Devuelve (errores, avisos, resumen) a partir del JSON de ffprobe. Función pura."""
    errs, warns = [], []
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        return ["no hay pista de video"], warns, {}
    w, h = int(video.get("width", 0)), int(video.get("height", 0))
    fps = parse_rate(video.get("avg_frame_rate", "0/1"))
    dur = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    if w < min_w or h < min_h:
        errs.append("resolución %dx%d: mínimo %dx%d" % (w, h, min_w, min_h))
    if not min_s <= dur <= max_s:
        errs.append("duración %.1f s: debe estar entre %.0f y %.0f s" % (dur, min_s, max_s))
    if fps < 29.5:
        errs.append("%.2f fps: menos de 30" % fps)
    elif fps < 59.0:
        warns.append("%.2f fps: el objetivo es 60" % fps)
    if audio is None:
        warns.append("sin pista de audio")
    summary = {"width": w, "height": h, "fps": round(fps, 2), "duration_s": round(dur, 2),
               "codec": video.get("codec_name"), "audio": bool(audio)}
    return errs, warns, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--min-res", default="1920x1080")
    ap.add_argument("--min-s", type=float, default=30.0)
    ap.add_argument("--max-s", type=float, default=60.0)
    a = ap.parse_args(argv)
    mw, mh = (int(p) for p in a.min_res.lower().split("x"))
    try:
        info = probe(a.video)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
        print("VIDEO_FAIL no se pudo leer el video: %s" % e)
        return 1
    if info is None:
        print("ffprobe no está instalado: verificación omitida (winget install Gyan.FFmpeg).")
        return 3
    errs, warns, summary = evaluate(info, mw, mh, a.min_s, a.max_s)
    print(json.dumps(summary))
    for w in warns:
        print("AVISO", w)
    for e in errs:
        print("ERROR", e)
    print("VIDEO_FAIL" if errs else "VIDEO_OK")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
