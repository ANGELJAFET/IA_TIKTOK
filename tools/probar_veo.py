"""Prueba rápida: genera una imagen de una fruta con Gemini y la anima con Veo (1 clip)."""
import sys
from pathlib import Path

import yaml
from google import genai

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import animacion, imagenes  # noqa: E402

cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
client = genai.Client()
out = Path("prueba_veo"); out.mkdir(exist_ok=True)
prompt = ("3D animated cartoon style like a Pixar movie, an anthropomorphic pineapple woman with big eyes "
          "arguing angrily with an anthropomorphic mango man in a colorful kitchen, vertical composition")
img = imagenes.generar_imagen(client, cfg["modelos"]["imagen"], prompt, out / "img")
print("imagen ok:", img)
vid = animacion.animar(client, "auto", img, prompt, out / "clip.mp4", 8)
print("VIDEO OK:", vid, vid.stat().st_size, "bytes")
