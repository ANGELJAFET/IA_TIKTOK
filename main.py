"""Pipeline completo: serie de 7 partes → guion → imágenes → voz → montaje → TikTok.

    python main.py                 # genera y publica
    python main.py --solo-generar  # genera el video pero NO lo sube (para probar)
    python main.py --tema "Betrayals that changed history"   # empieza una serie nueva con ese tema
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from google import genai

from pipeline import analitica, guion, imagenes, montaje, pexels, tiktok, voz

RAIZ = Path(__file__).parent
HISTORIAL = RAIZ / "data" / "historial.json"
TEMAS = RAIZ / "data" / "temas.txt"
SERIE = RAIZ / "data" / "serie_actual.json"


def siguiente_tema_en_cola() -> str | None:
    """Mira la primera línea de data/temas.txt (si hay), sin quitarla todavía."""
    if not TEMAS.exists():
        return None
    lineas = TEMAS.read_text(encoding="utf-8").splitlines()
    validas = [l for l in lineas if l.strip() and not l.lstrip().startswith("#")]
    if not validas:
        return None
    return validas[0].strip()


def quitar_de_cola(tema: str):
    """Saca el tema de la cola solo cuando su serie ya arrancó de verdad."""
    if not tema or not TEMAS.exists():
        return
    lineas = TEMAS.read_text(encoding="utf-8").splitlines()
    if tema in lineas:
        lineas.remove(tema)
        TEMAS.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-generar", action="store_true")
    ap.add_argument("--tema")
    ap.add_argument("--solo-estadisticas", action="store_true", help="solo actualiza los datos del panel")
    args = ap.parse_args()

    cfg = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))
    historial = json.loads(HISTORIAL.read_text(encoding="utf-8")) if HISTORIAL.exists() else []
    client = genai.Client()  # lee GEMINI_API_KEY

    sello = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    trabajo = RAIZ / "salida" / sello
    trabajo.mkdir(parents=True, exist_ok=True)

    if not args.solo_generar and not os.environ.get("TIKTOK_REFRESH_TOKEN"):
        print("▶ TikTok aún no está configurado (falta TIKTOK_REFRESH_TOKEN): solo se genera el video")
        args.solo_generar = True

    tok = None
    if os.environ.get("TIKTOK_REFRESH_TOKEN"):
        tok = tiktok.refrescar_token(os.environ["TIKTOK_CLIENT_KEY"], os.environ["TIKTOK_CLIENT_SECRET"],
                                     os.environ["TIKTOK_REFRESH_TOKEN"])
        if tok.get("refresh_token") and tok["refresh_token"] != os.environ["TIKTOK_REFRESH_TOKEN"]:
            (RAIZ / ".nuevo_refresh_token").write_text(tok["refresh_token"])

    if tok:
        try:
            print("▶ Actualizando estadísticas del panel")
            analitica.guardar_panel(tok["access_token"], historial, RAIZ / "data" / "videos.json")
            analitica.actualizar(tok["access_token"], historial, RAIZ / "data" / "rendimiento.json")
        except Exception as e:
            print(f"  (sin estadísticas: {e})")
    if args.solo_estadisticas:
        return

    # 1. Serie: continúa la actual o planea una nueva (7 partes, 1 por día)
    plan = json.loads(SERIE.read_text(encoding="utf-8")) if SERIE.exists() else None
    tema_de_cola = None
    if args.tema or not plan or plan["parte_actual"] >= len(plan["partes"]):
        tema_de_cola = None if args.tema else siguiente_tema_en_cola()
        tema = args.tema or tema_de_cola
        print(f"▶ Nueva serie ({'tema: ' + tema if tema else 'tema automático'})")
        series_previas = list(dict.fromkeys(h.get("serie", h["tema"]) for h in historial))
        aprendizaje = ""
        rend = RAIZ / "data" / "rendimiento.json"
        if rend.exists():
            aprendizaje = analitica.resumen_para_ia(json.loads(rend.read_text(encoding="utf-8")))
        plan = guion.planear_serie(client, cfg, tema, series_previas, aprendizaje)
        print(f"  serie: {plan['serie']} ({len(plan['partes'])} partes)")
    print(f"▶ Guion parte {plan['parte_actual'] + 1}/{len(plan['partes'])}")
    g = guion.generar_parte(client, cfg, plan)
    (trabajo / "guion.json").write_text(json.dumps(g, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {g['tema']}")

    # 2. Imágenes + voz por escena
    fuente = cfg.get("visuales", "pexels")
    escenas, usados = [], set()
    for i, e in enumerate(g["escenas"]):
        print(f"▶ Escena {i + 1}/{len(g['escenas'])} ({fuente})")
        consultas = [e.get("busqueda", ""), " ".join(e.get("busqueda", "").split()[:2]), plan["serie"]]
        if fuente == "gemini":
            try:
                img, tipo = imagenes.generar_imagen(client, cfg["modelos"]["imagen"], e["imagen"], trabajo / f"img_{i:02d}"), "imagen"
            except RuntimeError as err:
                if os.environ.get("PEXELS_API_KEY"):
                    print(f"  Gemini falló ({str(err)[:80]}...); usando Pexels")
                    img, tipo = pexels.visual_para_escena(consultas, trabajo / f"vis_{i:02d}", usados)
                else:
                    print(f"  Gemini falló ({str(err)[:80]}...); usando fondo de color")
                    img, tipo = montaje.fondo_color(trabajo / f"fondo_{i:02d}.png", cfg["video"], i), "imagen"
        else:
            img, tipo = pexels.visual_para_escena(consultas, trabajo / f"vis_{i:02d}", usados)
        mp3 = trabajo / f"voz_{i:02d}.mp3"
        palabras = voz.narrar(e["narracion"], cfg["voz"]["nombre"], cfg["voz"]["velocidad"], mp3)
        escenas.append({"imagen": img, "tipo": tipo, "audio": mp3, "palabras": palabras})

    # 3. Montaje
    print("▶ Montaje")
    final = montaje.montar(trabajo, escenas, cfg, RAIZ / "assets" / "musica")
    dur = montaje.duracion(final)
    print(f"  video listo: {final} ({dur:.1f}s)")

    tags = list(dict.fromkeys(g.get("hashtags", []) + cfg["canal"]["hashtags_base"]))
    titulo = f"{g['titulo']} {' '.join(tags)}"
    registro = {"fecha": sello, "serie": plan["serie"], "parte": g["parte"], "tema": g["tema"],
                "titulo": titulo, "duracion": round(dur, 1)}

    if args.solo_generar:
        print("▶ Modo prueba: no se sube a TikTok")
        registro["estado"] = "solo_generado"
    else:
        # 4. TikTok
        print(f"▶ Subiendo a TikTok (modo {cfg['tiktok']['modo']})")
        try:
            pid = tiktok.subir(tok["access_token"], final, titulo, cfg["tiktok"], dur)
            estado = tiktok.esperar_estado(tok["access_token"], pid)
            registro.update(publish_id=pid, estado=estado)
            print(f"  ✅ {estado} (publish_id {pid})")
        except tiktok.TikTokError as e:
            registro.update(estado="error", error=str(e))
            print(f"  ❌ {e}")

    # Resumen visible en GitHub (pestaña Actions) con el texto listo para copiar
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"## {g['tema']}\n\n**Estado:** {registro.get('estado')} · **Duración:** {dur:.0f}s\n\n"
                    f"**Descripción para TikTok (cópiala al publicar el borrador):**\n\n```\n{titulo}\n```\n\n"
                    "El video completo está abajo en *Artifacts*.\n")

    # La serie solo avanza cuando el video se publicó (las pruebas no gastan partes)
    if registro.get("estado") not in ("error", "solo_generado"):
        plan["parte_actual"] += 1
        plan["resumenes"].append(g.get("resumen", ""))
        SERIE.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
        quitar_de_cola(tema_de_cola)

    historial.append(registro)
    HISTORIAL.write_text(json.dumps(historial, indent=2, ensure_ascii=False), encoding="utf-8")
    if registro.get("estado") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
