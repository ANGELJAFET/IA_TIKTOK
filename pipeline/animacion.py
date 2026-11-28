"""Anima una escena con Veo a partir de la imagen del personaje (así se ve igual en todo el video)."""
import time
from pathlib import Path

from google import genai
from google.genai import types

_MODELO_CACHE: str | None = None


CANDIDATOS = [
    "veo-3.1-lite-generate-preview", "veo-3.1-fast-generate-preview", "veo-3.1-generate-preview",
    "veo-3.0-fast-generate-001", "veo-3.0-generate-001", "veo-2.0-generate-001",
]


def candidatos(client: genai.Client, preferido: str) -> list[str]:
    """Modelos a probar en orden (del más barato al más caro)."""
    if preferido and preferido != "auto":
        return [preferido]
    if _MODELO_CACHE:
        return [_MODELO_CACHE]
    lista = []
    try:
        lista = [m.name.replace("models/", "") for m in client.models.list() if "veo" in m.name]
    except Exception:
        pass
    orden = sorted(lista, key=lambda n: (0 if "lite" in n else 1 if "fast" in n else 2, n))
    return list(dict.fromkeys(orden + CANDIDATOS))


def animar(client: genai.Client, modelo: str, imagen: Path, prompt: str, destino: Path,
           segundos: int = 8, max_espera: int = 600) -> Path:
    global _MODELO_CACHE
    mime = "image/png" if imagen.suffix == ".png" else "image/jpeg"
    texto = (f"{prompt}. The fruit characters move and act like people: they talk with mouth movement, "
             f"gesture with their arms, walk and show emotions. Smooth cinematic camera. No text on screen.")
    op, ultimo = None, None
    for m in candidatos(client, modelo):
        try:
            op = client.models.generate_videos(
                model=m,
                prompt=texto,
                image=types.Image(image_bytes=imagen.read_bytes(), mime_type=mime),
                config=types.GenerateVideosConfig(aspect_ratio="9:16", duration_seconds=segundos, number_of_videos=1),
            )
            if _MODELO_CACHE != m:
                print(f"  modelo de video: {m}")
            _MODELO_CACHE = m
            break
        except Exception as e:
            ultimo = e
            txt = str(e)
            if any(k in txt for k in ("404", "NOT_FOUND", "not found", "not supported", "INVALID_ARGUMENT")):
                continue  # este modelo no existe o no acepta la petición: probar el siguiente
            raise
    if op is None:
        raise RuntimeError(f"Ningún modelo Veo funcionó: {ultimo}")
    fin = time.time() + max_espera
    while not op.done:
        if time.time() > fin:
            raise RuntimeError("Veo tardó demasiado")
        time.sleep(10)
        op = client.operations.get(op)
    if getattr(op, "error", None):
        raise RuntimeError(f"Veo: {op.error}")
    videos = getattr(op.response, "generated_videos", None) or []
    if not videos:
        raise RuntimeError("Veo no devolvió video (posible filtro de contenido)")
    client.files.download(file=videos[0].video)
    videos[0].video.save(str(destino))
    return destino
