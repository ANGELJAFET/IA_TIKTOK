"""Pipeline completo: tema → guion → imágenes → voz → montaje → TikTok.

    python main.py                 # genera y publica
    python main.py --solo-generar  # genera el video pero NO lo sube (para probar)
    python main.py --tema "Why octopuses have three hearts"
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from google import genai

from pipeline import guion, imagenes, montaje, tiktok, voz

RAIZ = Path(__file__).parent
HISTORIAL = RAIZ / "data" / "historial.json"
TEMAS = RAIZ / "data" / "temas.txt"


def siguiente_tema_en_cola() -> str | None:
    """Toma la primera línea de data/temas.txt (si hay) y la quita de la cola."""
    if not TEMAS.exists():
        return None
    lineas = TEMAS.read_text(encoding="utf-8").splitlines()
    validas = [l for l in lineas if l.strip() and not l.lstrip().startswith("#")]
    if not validas:
        return None
    tema = validas[0].strip()
    lineas.remove(validas[0])
    TEMAS.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return tema


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-generar", action="store_true")
    ap.add_argument("--tema")
    args = ap.parse_args()

    cfg = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))
    historial = json.loads(HISTORIAL.read_text(encoding="utf-8")) if HISTORIAL.exists() else []
    client = genai.Client()  # lee GEMINI_API_KEY

    sello = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    trabajo = RAIZ / "salida" / sello
    trabajo.mkdir(parents=True, exist_ok=True)

    # 1. Guion
    tema = args.tema or siguiente_tema_en_cola()
    print(f"▶ Guion ({'tema dado: ' + tema if tema else 'tema automático'})")
    g = guion.generar_guion(client, cfg, tema, [h["tema"] for h in historial])
    (trabajo / "guion.json").write_text(json.dumps(g, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  tema: {g['tema']}")

    # 2. Imágenes + voz por escena
    escenas = []
    for i, e in enumerate(g["escenas"]):
        print(f"▶ Escena {i + 1}/{len(g['escenas'])}")
        img = imagenes.generar_imagen(client, cfg["modelos"]["imagen"], e["imagen"], trabajo / f"img_{i:02d}")
        mp3 = trabajo / f"voz_{i:02d}.mp3"
        palabras = voz.narrar(e["narracion"], cfg["voz"]["nombre"], cfg["voz"]["velocidad"], mp3)
        escenas.append({"imagen": img, "audio": mp3, "palabras": palabras})

    # 3. Montaje
    print("▶ Montaje")
    final = montaje.montar(trabajo, escenas, cfg, RAIZ / "assets" / "musica")
    dur = montaje.duracion(final)
    print(f"  video listo: {final} ({dur:.1f}s)")

    tags = list(dict.fromkeys(g.get("hashtags", []) + cfg["canal"]["hashtags_base"]))
    titulo = f"{g['titulo']} {' '.join(tags)}"
    registro = {"fecha": sello, "tema": g["tema"], "titulo": titulo, "duracion": round(dur, 1)}

    if not args.solo_generar and not os.environ.get("TIKTOK_REFRESH_TOKEN"):
        print("▶ TikTok aún no está configurado (falta TIKTOK_REFRESH_TOKEN): solo se genera el video")
        args.solo_generar = True

    if args.solo_generar:
        print("▶ Modo prueba: no se sube a TikTok")
        registro["estado"] = "solo_generado"
    else:
        # 4. TikTok
        print("▶ Subiendo a TikTok")
        tok = tiktok.refrescar_token(os.environ["TIKTOK_CLIENT_KEY"], os.environ["TIKTOK_CLIENT_SECRET"],
                                     os.environ["TIKTOK_REFRESH_TOKEN"])
        if tok.get("refresh_token") and tok["refresh_token"] != os.environ["TIKTOK_REFRESH_TOKEN"]:
            (RAIZ / ".nuevo_refresh_token").write_text(tok["refresh_token"])
        try:
            pid = tiktok.subir(tok["access_token"], final, titulo, cfg["tiktok"], dur)
            estado = tiktok.esperar_estado(tok["access_token"], pid)
            registro.update(publish_id=pid, estado=estado)
            print(f"  ✅ {estado} (publish_id {pid})")
        except tiktok.TikTokError as e:
            registro.update(estado="error", error=str(e))
            print(f"  ❌ {e}")

    historial.append(registro)
    HISTORIAL.write_text(json.dumps(historial, indent=2, ensure_ascii=False), encoding="utf-8")
    if registro.get("estado") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
