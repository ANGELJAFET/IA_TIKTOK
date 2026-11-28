"""Lee las estadísticas de tus videos (TikTok Display API) y calcula qué series gustan más."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://open.tiktokapis.com/v2"
CAMPOS = ("id,title,video_description,create_time,duration,cover_image_url,share_url,embed_link,"
          "view_count,like_count,comment_count,share_count")


def listar_videos(token: str, maximo: int = 100) -> list[dict]:
    videos, cursor = [], None
    while len(videos) < maximo:
        body = {"max_count": 20}
        if cursor:
            body["cursor"] = cursor
        r = requests.post(f"{API}/video/list/", params={"fields": CAMPOS}, json=body, timeout=30,
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        d = r.json()
        if d.get("error", {}).get("code") not in (None, "", "ok"):
            raise RuntimeError(f"video.list: {d['error']}")
        data = d.get("data", {})
        videos += data.get("videos", [])
        if not data.get("has_more"):
            break
        cursor = data.get("cursor")
    return videos


def puntaje(v: dict) -> float:
    """Comentarios y compartidos pesan más que un like: son las señales que más empujan el algoritmo."""
    vistas = v.get("view_count", 0)
    inter = v.get("like_count", 0) + 3 * v.get("comment_count", 0) + 5 * v.get("share_count", 0)
    return vistas + 20 * inter


def _norm(t: str) -> str:
    return re.sub(r"\W+", " ", (t or "").lower()).strip()


def _emparejar(historial: list[dict], videos: list[dict]) -> dict[str, list[dict]]:
    """Asocia cada video de TikTok a su serie: por el nombre en la descripción o,
    si lo publicaste desde borradores con otro texto, por la fecha (primer video
    publicado dentro de las 72 h siguientes a la subida)."""
    por_serie: dict[str, list[dict]] = {}
    usados = set()
    publicados = [h for h in historial if h.get("serie") and h.get("estado") not in ("error", "solo_generado")]
    for h in publicados:
        clave = _norm(h["serie"])
        v = next((v for v in videos if v["id"] not in usados and clave
                  and clave in _norm(v.get("video_description") or v.get("title"))), None)
        if not v:
            t0 = datetime.strptime(h["fecha"], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc).timestamp()
            candidatos = sorted((v for v in videos if v["id"] not in usados
                                 and t0 <= v.get("create_time", 0) <= t0 + 72 * 3600),
                                key=lambda v: v["create_time"])
            v = candidatos[0] if candidatos else None
        if v:
            usados.add(v["id"])
            por_serie.setdefault(h["serie"], []).append(v)
    return por_serie


def rendimiento_por_serie(historial: list[dict], videos: list[dict]) -> list[dict]:
    res = []
    for serie, vs in _emparejar(historial, videos).items():
        res.append({
            "serie": serie,
            "videos": len(vs),
            "vistas_promedio": round(sum(v.get("view_count", 0) for v in vs) / len(vs)),
            "likes": sum(v.get("like_count", 0) for v in vs),
            "comentarios": sum(v.get("comment_count", 0) for v in vs),
            "compartidos": sum(v.get("share_count", 0) for v in vs),
            "puntaje": round(sum(puntaje(v) for v in vs) / len(vs)),
        })
    return sorted(res, key=lambda x: x["puntaje"], reverse=True)


def resumen_para_ia(ranking: list[dict]) -> str:
    """Texto que se le pasa a Gemini al planear la próxima serie."""
    if len(ranking) < 2:
        return ""
    n_top = min(3, max(1, len(ranking) // 2))
    fmt = lambda rs: "; ".join(f"{r['serie']} (avg {r['vistas_promedio']} views)" for r in rs)
    top, flojo = fmt(ranking[:n_top]), fmt(ranking[n_top:][-2:])
    txt = f"PERFORMANCE DATA — our audience loved these series: {top}."
    if flojo:
        txt += f" These performed worst: {flojo}."
    return txt + (" Create a NEW series (different subject) that keeps what made the winners work "
                  "(type of topic, tone, angle). Avoid what the weak ones had in common.")


def actualizar(token: str, historial: list[dict], destino: Path) -> str:
    """Descarga estadísticas, guarda data/rendimiento.json y devuelve el resumen para la IA."""
    if not any(h.get("serie") for h in historial):
        return ""
    ranking = rendimiento_por_serie(historial, listar_videos(token))
    destino.write_text(json.dumps(ranking, indent=2, ensure_ascii=False), encoding="utf-8")
    for r in ranking[:5]:
        print(f"  {r['puntaje']:>8}  {r['serie']}  ({r['vistas_promedio']} vistas prom.)")
    return resumen_para_ia(ranking)


def guardar_panel(token: str, historial: list[dict], destino: Path) -> list[dict]:
    """Guarda data/videos.json con cada video publicado y su serie, para el panel web."""
    videos = listar_videos(token)
    serie_de = {}
    for serie, vs in _emparejar(historial, videos).items():
        for v in vs:
            serie_de[v["id"]] = serie
    partes = {}
    for h in historial:
        if h.get("serie"):
            partes.setdefault(h["serie"], []).append(h.get("parte"))
    salida = []
    for v in sorted(videos, key=lambda x: x.get("create_time", 0), reverse=True):
        salida.append({
            "id": v["id"],
            "titulo": v.get("title") or (v.get("video_description") or "")[:120],
            "fecha": v.get("create_time", 0),
            "duracion": v.get("duration", 0),
            "portada": v.get("cover_image_url", ""),
            "enlace": v.get("share_url", ""),
            "serie": serie_de.get(v["id"], ""),
            "vistas": v.get("view_count", 0),
            "likes": v.get("like_count", 0),
            "comentarios": v.get("comment_count", 0),
            "compartidos": v.get("share_count", 0),
        })
    ahora = int(datetime.now(timezone.utc).timestamp())
    # Histórico: un punto por video cuando cambian sus vistas (máx. 200 por video)
    hist_f = destino.parent / "historico_vistas.json"
    hist = json.loads(hist_f.read_text(encoding="utf-8")) if hist_f.exists() else {}
    for v in salida:
        serie = hist.setdefault(v["id"], [])
        if not serie or serie[-1][1] != v["vistas"]:
            serie.append([ahora, v["vistas"]])
            del serie[:-200]
    hist_f.write_text(json.dumps(hist, separators=(",", ":")), encoding="utf-8")
    destino.write_text(json.dumps({"actualizado": ahora, "videos": salida}, indent=2, ensure_ascii=False),
                       encoding="utf-8")
    print(f"  panel: {len(salida)} videos guardados")
    return salida
