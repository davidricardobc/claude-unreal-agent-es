"""Crea el preset de Movie Render Queue para tráiler: 1920x1080 mínimo, 60 fps, formato de edición.
Corre DENTRO de Unreal (Python de editor). Verificado en UE 5.8.4 (proyecto C++ en blanco, 9-nov-2026: preset PNG y render real de 240 PNG).
Sin verificar: lo marcado SV (el formato prores y las variables de consola).

Variables de entorno (todas opcionales):
  KIT_TRAILER_PRESET    nombre del asset (por defecto TrailerHD60), en /Game/Cine/Presets
  KIT_TRAILER_OUT       carpeta de salida de los fotogramas (por defecto <Proyecto>/Saved/TrailerRender)
  KIT_TRAILER_FORMAT    png (por defecto) | exr | prores (prores SV: necesita el plugin de códec)
  KIT_TRAILER_RES       "1920x1080" por defecto; nunca menos
  KIT_TRAILER_CVARS     variables de consola del render, "nombre=valor,nombre=valor" (por ejemplo para bajar Lumen con 6 GB;
                        comprobar cada nombre en la consola del editor: SV)
  KIT_TRAILER_TEMPORAL  muestras temporales (por defecto 8; bajar a 4 con 6 GB de VRAM)
Formato de edición: secuencia PNG de 8 bits (ligera, la lee cualquier editor) o EXR si se va a corregir color. Se pasa a MP4 con ffmpeg
(ver `shot_plan.py ffmpeg`).
"""
import os
import sys

PRESET_DIR = "/Game/Cine/Presets"


def parse_res(text):
    """'1920x1080' -> (1920, 1080). Rechaza menos de 1920x1080. Función pura."""
    w, h = (int(p) for p in text.lower().split("x"))
    if w < 1920 or h < 1080:
        raise ValueError("resolución %dx%d: el mínimo es 1920x1080" % (w, h))
    return w, h


def parse_cvars(text):
    """'a.b=1, c.d=0.5' -> [('a.b', 1.0), ('c.d', 0.5)]. Función pura; rechaza entradas mal formadas."""
    out = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        name, _, val = part.partition("=")
        if not name.strip() or not val.strip():
            raise ValueError("cvar mal formada: '%s' (usa nombre=valor)" % part)
        out.append((name.strip(), float(val)))
    return out


def main():
    try:
        import unreal
    except ImportError:
        print("KIT_FAIL este script corre dentro de Unreal")
        return 1
    name = os.environ.get("KIT_TRAILER_PRESET", "TrailerHD60")
    fmt = os.environ.get("KIT_TRAILER_FORMAT", "png").lower()
    w, h = parse_res(os.environ.get("KIT_TRAILER_RES", "1920x1080"))
    temporal = int(os.environ.get("KIT_TRAILER_TEMPORAL", "8"))
    out_dir = os.environ.get("KIT_TRAILER_OUT") or os.path.join(unreal.Paths.project_saved_dir(), "TrailerRender")
    path = "%s/%s" % (PRESET_DIR, name)
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        print("KIT_INFO ya existe, no se sobrescribe:", path)
        print("KIT_OK")
        return 0

    cls = getattr(unreal, "MoviePipelinePrimaryConfig", None) or getattr(unreal, "MoviePipelineMasterConfig", None)  # el nombre cambió entre versiones
    if cls is None:
        print("KIT_FAIL no hay clase de config de MRQ; activar el plugin Movie Render Queue")
        return 1
    cfg = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, PRESET_DIR, cls, None)  # create_asset con factory None funciona en 5.8.4
    if cfg is None:
        print("KIT_FAIL no se pudo crear el asset de config")
        return 1

    out = cfg.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
    out.output_resolution = unreal.IntPoint(w, h)
    out.use_custom_frame_rate = True
    out.output_frame_rate = unreal.FrameRate(60, 1)
    out.output_directory = unreal.DirectoryPath(out_dir)
    out.file_name_format = "{sequence_name}.{frame_number}"
    out.zero_pad_frame_numbers = 4

    cfg.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
    fmt_cls = {
        "png": "MoviePipelineImageSequenceOutput_PNG",
        "exr": "MoviePipelineImageSequenceOutput_EXR",
        "prores": "MoviePipelineAppleProResOutput",  # SV
    }.get(fmt)
    if fmt_cls is None or not hasattr(unreal, fmt_cls):
        print("KIT_FAIL formato '%s' no disponible (%s)" % (fmt, fmt_cls))
        return 1
    cfg.find_or_add_setting_by_class(getattr(unreal, fmt_cls))

    aa = cfg.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
    aa.spatial_sample_count = 1
    aa.temporal_sample_count = temporal
    aa.override_anti_aliasing = True

    cvars = parse_cvars(os.environ.get("KIT_TRAILER_CVARS", ""))
    if cvars:
        cv = cfg.find_or_add_setting_by_class(unreal.MoviePipelineConsoleVariableSetting)  # SV
        for n, v in cvars:
            cv.add_or_update_console_variable(n, v)  # SV

    unreal.EditorAssetLibrary.save_asset(path)
    print("KIT_INFO preset creado: %s (%dx%d, 60 fps, %s, salida %s)" % (path, w, h, fmt, out_dir))
    print("KIT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
