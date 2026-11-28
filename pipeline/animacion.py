"""Anima una escena con Veo (API REST de Gemini) a partir de la imagen del personaje,
así los personajes se ven iguales en todo el video.

La librería google-genai solo permite generate_videos en modo Vertex/Enterprise, por eso
aquí se llama directamente al endpoint predictLongRunning con la GEMINI_API_KEY."""
import base64
import os
import time
from pathlib import Path

import requests

API = "https://generativelanguage.googleapis.com/v1beta"
CANDIDATOS = [
    "veo-3.1-lite-generate-preview", "veo-3.1-fast-generate-preview", "veo-3.1-generate-preview",
    "veo-3.0-fast-generate-001", "veo-3.0-generate-001", "veo-2.0-generate-001",
]
_MODELO_OK: str | None = None
_FORMATO_OK: str | None = None


def _h() -> dict:
    return {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}


def _imagen(formato: str, b64: str, mime: str) -> dict:
    if formato == "inline":
        return {"inlineData": {"mimeType": mime, "data": b64}}
    return {"bytesBase64Encoded": b64, "mimeType": mime}


def _iniciar(modelo: str, prompt: str, b64: str, mime: str, segundos: int) -> str:
    """Lanza la generación y devuelve el nombre de la operación. Prueba formatos y modelos."""
    global _MODELO_OK, _FORMATO_OK
    modelos = [_MODELO_OK] if _MODELO_OK else ([modelo] if modelo and modelo != "auto" else CANDIDATOS)
    formatos = [_FORMATO_OK] if _FORMATO_OK else ["base64", "inline"]
    ultimo = ""
    for m in modelos:
        for f in formatos:
            body = {
                "instances": [{"prompt": prompt, "image": _imagen(f, b64, mime)}],
                "parameters": {"aspectRatio": "9:16", "durationSeconds": segundos, "sampleCount": 1},
            }
            r = requests.post(f"{API}/models/{m}:predictLongRunning", headers=_h(), json=body, timeout=120)
            if r.ok and "name" in r.json():
                if _MODELO_OK != m:
                    print(f"  modelo de video: {m}")
                _MODELO_OK, _FORMATO_OK = m, f
                return r.json()["name"]
            ultimo = f"{m} [{f}] HTTP {r.status_code}: {r.text[:300]}"
            print(f"  Veo probó {ultimo[:200]}")
            if r.status_code == 404:
                break  # el modelo no existe: siguiente modelo
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError(ultimo)
    raise RuntimeError(f"Veo no aceptó la petición: {ultimo}")


def animar(client, modelo: str, imagen: Path, prompt: str, destino: Path,
           segundos: int = 8, max_espera: int = 600) -> Path:
    mime = "image/png" if imagen.suffix == ".png" else "image/jpeg"
    b64 = base64.b64encode(imagen.read_bytes()).decode()
    texto = (f"{prompt}. The fruit characters move and act like people: they talk with mouth movement, "
             f"gesture with their arms, walk and show emotions. Smooth cinematic camera. No text on screen.")
    op = _iniciar(modelo, texto, b64, mime, segundos)

    fin = time.time() + max_espera
    while True:
        d = requests.get(f"{API}/{op}", headers=_h(), timeout=60).json()
        if d.get("done"):
            break
        if time.time() > fin:
            raise RuntimeError("Veo tardó demasiado")
        time.sleep(10)
    if "error" in d:
        raise RuntimeError(f"Veo: {d['error']}")
    resp = d.get("response", {})
    muestras = (resp.get("generateVideoResponse", {}).get("generatedSamples")
                or resp.get("generatedVideos") or resp.get("videos") or [])
    if not muestras:
        raise RuntimeError(f"Veo no devolvió video (posible filtro de contenido): {str(resp)[:300]}")
    v = muestras[0].get("video", muestras[0])
    if v.get("uri"):
        r = requests.get(v["uri"], headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                         timeout=300, allow_redirects=True)
        r.raise_for_status()
        destino.write_bytes(r.content)
    elif v.get("bytesBase64Encoded"):
        destino.write_bytes(base64.b64decode(v["bytesBase64Encoded"]))
    else:
        raise RuntimeError(f"Respuesta de Veo sin video: {str(v)[:300]}")
    return destino
