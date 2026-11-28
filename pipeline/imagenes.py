"""Genera una imagen vertical por escena con Gemini (Nano Banana)."""
import time
from pathlib import Path

from google import genai
from google.genai import types


def _config(con_aspecto: bool):
    kw = {"response_modalities": ["IMAGE"]}
    if con_aspecto:
        try:
            kw["image_config"] = types.ImageConfig(aspect_ratio="9:16")
        except Exception:
            pass
    return types.GenerateContentConfig(**kw)


def generar_imagen(client: genai.Client, modelo: str, prompt: str, destino: Path) -> Path:
    prompt = f"Vertical 9:16 image. {prompt}. No text, no watermark."
    ultimo_error = None
    for intento in range(4):
        try:
            r = client.models.generate_content(
                model=modelo, contents=prompt, config=_config(con_aspecto=intento < 2)
            )
            for parte in r.candidates[0].content.parts:
                if getattr(parte, "inline_data", None) and parte.inline_data.data:
                    ext = ".png" if "png" in (parte.inline_data.mime_type or "") else ".jpg"
                    ruta = destino.with_suffix(ext)
                    ruta.write_bytes(parte.inline_data.data)
                    return ruta
            ultimo_error = "la respuesta no trajo imagen"
        except Exception as e:  # cuota, filtro de seguridad, red...
            ultimo_error = e
            if any(k in str(e) for k in ("RESOURCE_EXHAUSTED", "PERMISSION_DENIED", "API_KEY", "billing")):
                break  # sin cuota o sin permiso: reintentar no sirve
        print(f"  imagen falló (intento {intento + 1}): {ultimo_error}")
        time.sleep(5 * (intento + 1))
    raise RuntimeError(f"No se pudo generar la imagen: {ultimo_error}")
