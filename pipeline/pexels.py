"""Videos y fotos de stock gratis desde Pexels (https://www.pexels.com/api/)."""
import os
from pathlib import Path

import requests

API = "https://api.pexels.com"


def _h() -> dict:
    return {"Authorization": os.environ["PEXELS_API_KEY"]}


def _mejor_archivo(video: dict) -> dict | None:
    """Archivo mp4 vertical más cercano a 1080x1920 sin pasarse de 4K."""
    archivos = [f for f in video.get("video_files", [])
                if f.get("file_type") == "video/mp4" and f.get("height") and f.get("width")
                and f["height"] >= f["width"] and f["height"] <= 2160]
    if not archivos:
        return None
    return min(archivos, key=lambda f: abs(f["height"] - 1920))


def buscar_video(consulta: str, destino: Path, usados: set, min_seg: float = 4) -> Path | None:
    r = requests.get(f"{API}/videos/search", headers=_h(), timeout=30,
                     params={"query": consulta, "orientation": "portrait", "per_page": 15})
    r.raise_for_status()
    for v in r.json().get("videos", []):
        if v["id"] in usados or v.get("duration", 0) < min_seg:
            continue
        f = _mejor_archivo(v)
        if not f:
            continue
        ruta = destino.with_suffix(".mp4")
        with requests.get(f["link"], stream=True, timeout=120) as d:
            d.raise_for_status()
            with open(ruta, "wb") as out:
                for chunk in d.iter_content(1 << 20):
                    out.write(chunk)
        usados.add(v["id"])
        return ruta
    return None


def buscar_foto(consulta: str, destino: Path, usados: set) -> Path | None:
    r = requests.get(f"{API}/v1/search", headers=_h(), timeout=30,
                     params={"query": consulta, "orientation": "portrait", "per_page": 15})
    r.raise_for_status()
    for p in r.json().get("photos", []):
        if p["id"] in usados:
            continue
        ruta = destino.with_suffix(".jpg")
        ruta.write_bytes(requests.get(p["src"]["large2x"], timeout=60).content)
        usados.add(p["id"])
        return ruta
    return None


def visual_para_escena(consultas: list[str], destino: Path, usados: set) -> tuple[Path, str]:
    """Prueba cada consulta: primero video, luego foto. Devuelve (ruta, 'video'|'imagen')."""
    for q in consultas:
        if q and (ruta := buscar_video(q, destino, usados)):
            return ruta, "video"
    for q in consultas:
        if q and (ruta := buscar_foto(q, destino, usados)):
            return ruta, "imagen"
    raise RuntimeError(f"Pexels no encontró nada para: {consultas}")
