"""Genera series (plan de N partes) y el guion de cada parte con Gemini."""
import json
import re

from google import genai
from google.genai import types

PROMPT_SERIE = """You plan multi-part TikTok series for a faceless channel.
Niche: {nicho}
Audience: {publico}
Language: {idioma}

Create a {partes}-part series. One video per day; each part must stand alone but make viewers want the next one.
Series theme: {tema}
(If the theme is in another language or very broad, turn it into a specific, gripping English series for this niche.)

Rules:
- Facts must be TRUE and widely verifiable.
- Each part covers a DIFFERENT angle/story; build toward the most shocking part at the end.
- Define ONE visual style that all parts will share so the series looks consistent.

Do NOT repeat these previous series: {historial}

Return ONLY JSON:
{{
  "serie": "catchy series title in English",
  "estilo_visual": "one sentence visual style for every image in the series",
  "hashtags": ["#tag1", "#tag2"],
  "partes": [{{"titulo": "part title", "enfoque": "what this part reveals, 1-2 sentences"}}]
}}"""

PROMPT_PARTE = """You are a viral TikTok scriptwriter for a faceless channel.
Audience: {publico}. Language: {idioma}.

Series: "{serie}" — this is PART {n} OF {total}.
This part: {titulo} — {enfoque}
Previous parts (for continuity, do not repeat their facts): {anteriores}
Next part teaser: {siguiente}

Rules:
- Exactly {escenas} scenes. Total narration about {palabras} words.
- Scene 1 starts with "Part {n}." then a scroll-stopping hook in under 14 words.{recap}
- {cierre}
- Facts must be TRUE and widely verifiable. No made-up numbers. Simple, punchy sentences.
- For each scene write an image prompt in English using this style: {estilo}. No text, letters or logos. No real famous people's faces.

Return ONLY JSON:
{{
  "titulo": "TikTok caption, max 110 chars, with 1 emoji (do not add the part number)",
  "resumen": "one sentence summary of what this part revealed",
  "escenas": [{{"narracion": "...", "imagen": "..."}}]
}}"""


def _json(texto: str) -> dict:
    m = re.search(r"\{.*\}", texto.strip(), re.S)
    if not m:
        raise ValueError(f"Gemini no devolvió JSON: {texto[:300]}")
    return json.loads(m.group(0))


def _pedir_json(client, modelo: str, prompt: str, validar) -> dict:
    for intento in range(3):
        r = client.models.generate_content(
            model=modelo, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.9),
        )
        try:
            d = _json(r.text)
            if validar(d):
                return d
            print(f"  respuesta incompleta (intento {intento + 1})")
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  JSON inválido (intento {intento + 1}): {e}")
    raise RuntimeError("Gemini no devolvió una respuesta válida")


def planear_serie(client: genai.Client, cfg: dict, tema: str | None, historial: list[str]) -> dict:
    canal = cfg["canal"]
    partes = cfg["serie"]["partes"]
    tema = tema or f"pick a fresh, specific and surprising topic within: {canal['nicho']}"
    prompt = PROMPT_SERIE.format(
        nicho=canal["nicho"], publico=canal["publico"], idioma=canal["idioma"], partes=partes,
        tema=tema, historial="; ".join(historial[-60:]) or "none",
    )
    plan = _pedir_json(client, cfg["modelos"]["texto"], prompt,
                       lambda d: len(d.get("partes", [])) >= partes and d.get("serie"))
    plan["partes"] = plan["partes"][:partes]
    plan["estilo_visual"] = f"{plan.get('estilo_visual', '')} {canal['estilo_visual']}".strip()
    plan["parte_actual"] = 0  # partes ya publicadas
    plan["resumenes"] = []
    return plan


def _cierre(cfg: dict, n: int, ultima: bool) -> str:
    cta = cfg.get("cta", {})
    if ultima:
        txt = "Last scene wraps up the whole series and says: \"Follow for the next series.\""
    else:
        txt = f"Last scene teases part {n + 1} and says: \"Follow so you don't miss part {n + 1} tomorrow.\""
        if cta.get("comentar_parte"):
            txt += f" Also ask viewers to comment \"PART {n + 1}\" if they want it."
    if cta.get("apoyo"):
        txt += f" End with this exact short line: \"{cta['apoyo']}\""
    return txt


def generar_parte(client: genai.Client, cfg: dict, plan: dict) -> dict:
    v = cfg["video"]
    n = plan["parte_actual"] + 1
    total = len(plan["partes"])
    p = plan["partes"][n - 1]
    ultima = n == total
    prompt = PROMPT_PARTE.format(
        publico=cfg["canal"]["publico"], idioma=cfg["canal"]["idioma"],
        serie=plan["serie"], n=n, total=total, titulo=p["titulo"], enfoque=p["enfoque"],
        anteriores=" | ".join(plan["resumenes"]) or "none (this is the first part)",
        siguiente="none — this is the finale" if ultima else plan["partes"][n]["titulo"],
        escenas=v["escenas"], palabras=v["palabras_objetivo"], estilo=plan["estilo_visual"],
        recap="" if n == 1 else " Scene 1 may briefly connect to the previous part in a few words.",
        cierre=_cierre(cfg, n, ultima),
    )
    g = _pedir_json(client, cfg["modelos"]["texto"], prompt, lambda d: len(d.get("escenas", [])) >= 2)
    g["escenas"] = g["escenas"][: v["escenas"]]
    g["titulo"] = f"{plan['serie']} — Part {n}/{total}: {g['titulo']}"
    g["hashtags"] = plan.get("hashtags", [])
    g["tema"] = f"{plan['serie']} (part {n}/{total})"
    g["parte"] = n
    return g
