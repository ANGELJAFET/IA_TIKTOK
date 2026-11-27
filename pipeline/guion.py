"""Genera tema + guion por escenas con Gemini."""
import json
import re

from google import genai
from google.genai import types

PROMPT = """You are a viral TikTok scriptwriter for a faceless channel.
Niche: {nicho}
Audience: {publico}
Language: {idioma}

Write ONE short video about: {tema}

Rules:
- Exactly {escenas} scenes. Total narration about {palabras} words.
- Scene 1 is a scroll-stopping hook (a surprising claim or question) in under 12 words.
- Last scene ends with a short call to action (e.g. "Follow for more facts like this.").
- Facts must be TRUE and widely verifiable. No made-up numbers.
- Simple, punchy sentences. American English, US units and references.
- For each scene write an image prompt in English: {estilo}. No text, letters or logos in the image. No real famous people.

Do NOT repeat any of these previous topics: {historial}

Return ONLY JSON with this shape:
{{
  "tema": "short topic title",
  "titulo": "TikTok caption, max 120 chars, with 1 emoji",
  "hashtags": ["#tag1", "#tag2", "#tag3"],
  "escenas": [{{"narracion": "...", "imagen": "..."}}]
}}"""

PROMPT_TEMA = """Suggest ONE fresh, specific topic for a {nicho} TikTok aimed at {publico}.
It must be surprising and true. Avoid these topics: {historial}
Answer with the topic only, one line."""


def _json(texto: str) -> dict:
    texto = texto.strip()
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        raise ValueError(f"Gemini no devolvió JSON: {texto[:300]}")
    return json.loads(m.group(0))


def generar_guion(client: genai.Client, cfg: dict, tema: str | None, historial: list[str]) -> dict:
    canal, v = cfg["canal"], cfg["video"]
    hist = "; ".join(historial[-80:]) or "none"
    modelo = cfg["modelos"]["texto"]

    if not tema:
        r = client.models.generate_content(
            model=modelo,
            contents=PROMPT_TEMA.format(nicho=canal["nicho"], publico=canal["publico"], historial=hist),
        )
        tema = r.text.strip().strip('"')

    prompt = PROMPT.format(
        nicho=canal["nicho"], publico=canal["publico"], idioma=canal["idioma"], tema=tema,
        escenas=v["escenas"], palabras=v["palabras_objetivo"], estilo=canal["estilo_visual"], historial=hist,
    )
    for intento in range(3):
        r = client.models.generate_content(
            model=modelo,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.9),
        )
        try:
            g = _json(r.text)
            if len(g.get("escenas", [])) >= 2:
                g["escenas"] = g["escenas"][: v["escenas"]]
                return g
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  guion inválido (intento {intento + 1}): {e}")
    raise RuntimeError("No se pudo generar un guion válido")
