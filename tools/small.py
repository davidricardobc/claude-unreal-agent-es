"""Reduce capturas para verlas: python small.py <png> [ancho] [salida] -> small.jpg (o la salida indicada)"""
import sys
from PIL import Image
src = sys.argv[1]; w = int(sys.argv[2]) if len(sys.argv) > 2 else 960
out = sys.argv[3] if len(sys.argv) > 3 else "small.jpg"
im = Image.open(src).convert("RGB"); im = im.resize((w, int(im.height * w / im.width))); im.save(out, quality=85); print(out)
