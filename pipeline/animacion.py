"""Anima una escena con Veo a partir de la imagen del personaje (así se ve igual en todo el video)."""
import time
from pathlib import Path

from google import genai
from google.genai import types

_MODELO_CACHE: str | None = None


def elegir_modelo(client: genai.Client, preferido: str) -> str:
    """Si config dice "auto", busca el Veo más barato disponible (Lite > Fast > normal)."""
    global _MODELO_CACHE
    if preferido and preferido != "auto":
        return preferido
    if _MODELO_CACHE:
        return _MODELO_CACHE
    nombres = [m.name.replace("models/", "") for m in client.models.list() if "veo" in m.name]
    for clave in ("lite", "fast", ""):
        cand = sorted((n for n in nombres if clave in n), reverse=True)
        if cand:
            _MODELO_CACHE = cand[0]
            print(f"  modelo de video: {_MODELO_CACHE}")
            return _MODELO_CACHE
    raise RuntimeError("No hay modelos Veo disponibles para esta clave")


def animar(client: genai.Client, modelo: str, imagen: Path, prompt: str, destino: Path,
           segundos: int = 8, max_espera: int = 600) -> Path:
    modelo = elegir_modelo(client, modelo)
    mime = "image/png" if imagen.suffix == ".png" else "image/jpeg"
    texto = (f"{prompt}. The fruit characters move and act like people: they talk with mouth movement, "
             f"gesture with their arms, walk and show emotions. Smooth cinematic camera. No text on screen.")
    op = client.models.generate_videos(
        model=modelo,
        prompt=texto,
        image=types.Image(image_bytes=imagen.read_bytes(), mime_type=mime),
        config=types.GenerateVideosConfig(aspect_ratio="9:16", duration_seconds=segundos, number_of_videos=1),
    )
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
