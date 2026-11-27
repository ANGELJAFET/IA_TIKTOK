"""Narración con edge-tts (gratis) + tiempos de cada palabra para subtítulos."""
import asyncio
from pathlib import Path

import edge_tts


async def _tts(texto: str, voz: str, velocidad: str, destino: Path):
    palabras = []
    try:
        com = edge_tts.Communicate(texto, voz, rate=velocidad, boundary="WordBoundary")
    except TypeError:  # versiones viejas de edge-tts
        com = edge_tts.Communicate(texto, voz, rate=velocidad)
    with open(destino, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                ini = chunk["offset"] / 1e7
                palabras.append((ini, ini + chunk["duration"] / 1e7, chunk["text"]))
    return palabras


def narrar(texto: str, voz: str, velocidad: str, destino: Path) -> list[tuple[float, float, str]]:
    """Crea el mp3 y devuelve [(inicio, fin, palabra), ...] en segundos."""
    for intento in range(3):
        try:
            return asyncio.run(_tts(texto, voz, velocidad, destino))
        except Exception as e:
            print(f"  TTS falló (intento {intento + 1}): {e}")
    raise RuntimeError("edge-tts no respondió")
