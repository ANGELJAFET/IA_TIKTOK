"""Narración con edge-tts (gratis) + tiempos de cada palabra para subtítulos."""
import asyncio
from pathlib import Path

import edge_tts


async def _tts(texto: str, voz: str, velocidad: str, destino: Path, tono: str = "+0Hz"):
    palabras = []
    try:
        com = edge_tts.Communicate(texto, voz, rate=velocidad, pitch=tono, boundary="WordBoundary")
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


def narrar(texto: str, voz: str, velocidad: str, destino: Path, tono: str = "+0Hz") -> list[tuple[float, float, str]]:
    """Crea el mp3 y devuelve [(inicio, fin, palabra), ...] en segundos."""
    for intento in range(3):
        try:
            return asyncio.run(_tts(texto, voz, velocidad, destino, tono))
        except Exception as e:
            print(f"  TTS falló (intento {intento + 1}): {e}")
    raise RuntimeError("edge-tts no respondió")


# Voces por país (acento) y género. pais = código ISO del personaje en el elenco.
VOCES_PAIS = {
    "MX": {"M": ("es-MX-JorgeNeural", "+0Hz"), "F": ("es-MX-DaliaNeural", "+0Hz")},
    "CO": {"M": ("es-CO-GonzaloNeural", "+0Hz"), "F": ("es-CO-SalomeNeural", "+2Hz")},
    "AR": {"M": ("es-AR-TomasNeural", "+0Hz"), "F": ("es-AR-ElenaNeural", "+0Hz")},
    "VE": {"M": ("es-VE-SebastianNeural", "+0Hz"), "F": ("es-VE-PaolaNeural", "+0Hz")},
    "CU": {"M": ("es-CU-ManuelNeural", "+0Hz"), "F": ("es-CU-BelkysNeural", "+0Hz")},
    "HN": {"M": ("es-HN-CarlosNeural", "+0Hz"), "F": ("es-HN-KarlaNeural", "+0Hz")},
    "DO": {"M": ("es-DO-EmilioNeural", "+0Hz"), "F": ("es-DO-RamonaNeural", "+0Hz")},
    "PR": {"M": ("es-PR-VictorNeural", "+0Hz"), "F": ("es-PR-KarinaNeural", "+0Hz")},
    "CL": {"M": ("es-CL-LorenzoNeural", "+0Hz"), "F": ("es-CL-CatalinaNeural", "+0Hz")},
    "PE": {"M": ("es-PE-AlexNeural", "+0Hz"), "F": ("es-PE-CamilaNeural", "+0Hz")},
    "SV": {"M": ("es-SV-RodrigoNeural", "+0Hz"), "F": ("es-SV-LorenaNeural", "+0Hz")},
    "GT": {"M": ("es-GT-AndresNeural", "+0Hz"), "F": ("es-GT-MartaNeural", "+0Hz")},
    "ES": {"M": ("es-ES-AlvaroNeural", "+0Hz"), "F": ("es-ES-ElviraNeural", "+0Hz")},
}
VOCES = {g: [VOCES_PAIS[p][g] for p in VOCES_PAIS] for g in ("M", "F")}


def asignar_voces(elenco: list[dict], voz_narrador: str) -> dict:
    """{nombre: [voz, tono]}: usa el acento del país del personaje; si se repite, cambia el tono."""
    usadas, res = {voz_narrador}, {}
    for i, p in enumerate(elenco):
        g = (p.get("genero") or ("F" if i % 2 else "M")).upper()[:1]
        g = g if g in ("M", "F") else "M"
        pais = (p.get("pais") or "").upper()[:2]
        voz = VOCES_PAIS.get(pais, {}).get(g)
        if not voz or voz[0] in usadas:
            voz = next((v for v in VOCES[g] if v[0] not in usadas), voz or VOCES[g][0])
            if voz[0] in usadas:
                voz = (voz[0], "+10Hz" if g == "F" else "-10Hz")
        usadas.add(voz[0])
        res[p.get("nombre") or p.get("fruta") or f"p{i}"] = list(voz)
    return res


def _buscar_voz(quien: str, voces: dict):
    q = (quien or "").strip().lower()
    for nombre, v in voces.items():
        n = nombre.lower()
        if q == n or (q and (q in n or n in q)):
            return v
    return None


def narrar_escena(lineas: list[dict], voces: dict, narrador: str, velocidad: str, destino: Path):
    """Une las líneas de la escena, cada una con la voz de quien habla. Devuelve palabras con tiempos."""
    import subprocess
    partes, palabras, t = [], [], 0.0
    for i, l in enumerate(lineas):
        texto = (l.get("texto") or "").strip()
        if not texto:
            continue
        v = _buscar_voz(l.get("quien", ""), voces) if l.get("quien", "").lower() != "narrador" else None
        voz, tono = (v[0], v[1]) if v else (narrador, "+0Hz")
        mp3 = destino.with_name(f"{destino.stem}_{i:02d}.mp3")
        pal = narrar(texto, voz, velocidad, mp3, tono)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(mp3)], capture_output=True, text=True, check=True).stdout.strip())
        palabras += [(a + t, b + t, w) for a, b, w in pal]
        t += dur + 0.12
        partes.append(mp3)
    lista = destino.with_suffix(".txt")
    lista.write_text("".join(f"file '{p.name}'\nduration {0}\n" for p in []) +
                     "".join(f"file '{p.name}'\n" for p in partes))
    filtro = "".join(f"[{k}:a]apad=pad_dur=0.12[a{k}];" for k in range(len(partes))) + \
             "".join(f"[a{k}]" for k in range(len(partes))) + f"concat=n={len(partes)}:v=0:a=1[out]"
    cmd = ["ffmpeg", "-y"]
    for p in partes:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", filtro, "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "3", str(destino)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-800:])
    return palabras
