"""Subida a TikTok con la Content Posting API oficial."""
import time
from pathlib import Path

import requests

API = "https://open.tiktokapis.com/v2"
MB = 1024 * 1024


class TikTokError(RuntimeError):
    pass


def _check(r: requests.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        raise TikTokError(f"HTTP {r.status_code}: {r.text[:300]}")
    err = data.get("error", {})
    if r.status_code >= 400 or (err.get("code") not in (None, "", "ok")):
        raise TikTokError(f"{err.get('code')}: {err.get('message')} (log_id {err.get('log_id')})")
    return data


def refrescar_token(client_key: str, client_secret: str, refresh_token: str) -> dict:
    """Devuelve {'access_token', 'refresh_token', ...}. El access token dura 24 h."""
    r = requests.post(
        f"{API}/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"client_key": client_key, "client_secret": client_secret,
              "grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        raise TikTokError(f"No se pudo refrescar el token: {data}")
    return data


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}


def info_creador(token: str) -> dict:
    return _check(requests.post(f"{API}/post/publish/creator_info/query/", headers=_h(token), timeout=30))["data"]


def _chunks(tam: int) -> tuple[int, int]:
    if tam <= 64 * MB:
        return tam, 1
    chunk = 10 * MB
    return chunk, tam // chunk  # el último chunk absorbe el resto


def subir(token: str, video: Path, titulo: str, cfg_tt: dict, duracion_seg: float) -> str:
    tam = video.stat().st_size
    chunk, total = _chunks(tam)
    source = {"source": "FILE_UPLOAD", "video_size": tam, "chunk_size": chunk, "total_chunk_count": total}

    if cfg_tt["modo"] == "borrador":
        url_init = f"{API}/post/publish/inbox/video/init/"
        body = {"source_info": source}
    else:
        info = info_creador(token)
        maxdur = info.get("max_video_post_duration_sec", 600)
        if duracion_seg > maxdur:
            raise TikTokError(f"El video dura {duracion_seg:.0f}s y la cuenta permite {maxdur}s")
        opciones = info.get("privacy_level_options", [])
        privacidad = cfg_tt["privacidad"]
        if opciones and privacidad not in opciones:
            print(f"  privacidad {privacidad} no disponible; usando {opciones[0]}")
            privacidad = opciones[0]
        url_init = f"{API}/post/publish/video/init/"
        body = {
            "post_info": {
                "title": titulo[:2200],
                "privacy_level": privacidad,
                "disable_comment": cfg_tt["desactivar_comentarios"],
                "disable_duet": cfg_tt["desactivar_duo"],
                "disable_stitch": cfg_tt["desactivar_stitch"],
                "is_aigc": True,  # etiqueta "contenido generado por IA"
            },
            "source_info": source,
        }

    data = _check(requests.post(url_init, headers=_h(token), json=body, timeout=60))["data"]
    publish_id, upload_url = data["publish_id"], data["upload_url"]

    with open(video, "rb") as f:
        for i in range(total):
            ini = i * chunk
            fin = tam - 1 if i == total - 1 else ini + chunk - 1
            f.seek(ini)
            parte = f.read(fin - ini + 1)
            r = requests.put(upload_url, data=parte, timeout=300, headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(len(parte)),
                "Content-Range": f"bytes {ini}-{fin}/{tam}",
            })
            if r.status_code not in (200, 201, 206):
                raise TikTokError(f"Fallo subiendo chunk {i + 1}/{total}: HTTP {r.status_code} {r.text[:200]}")
    return publish_id


def esperar_estado(token: str, publish_id: str, max_seg: int = 300) -> str:
    fin = time.time() + max_seg
    estado = "?"
    while time.time() < fin:
        d = _check(requests.post(f"{API}/post/publish/status/fetch/", headers=_h(token),
                                 json={"publish_id": publish_id}, timeout=30))["data"]
        estado = d.get("status", "?")
        if estado in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            return estado
        if estado == "FAILED":
            raise TikTokError(f"TikTok rechazó el video: {d.get('fail_reason')}")
        time.sleep(10)
    return estado
