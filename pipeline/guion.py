"""Genera series (plan de N partes) y el guion de cada parte con Gemini."""
import json
import re
import time

from google import genai
from google.genai import types

PROMPT_SERIE = """Planeas series virales de TikTok para un canal sin rostro.
Formato del canal: {nicho}
Público: {publico}
Idioma de todo el contenido: {idioma}

Crea una serie de {partes} partes (un video por día). Cada parte debe entenderse sola pero dejar con ganas de la siguiente (cliffhanger).
Tema de la serie: {tema}

Reglas:
- Los personajes SIEMPRE son frutas con personalidad (ej. el Mango galán, la Piña chismosa, el Limón amargado). Define un elenco fijo de 3 a 5 frutas para toda la serie.
- Historias de drama, comedia, chisme y traiciones, al estilo de las novelas de frutas virales.
- Puedes hacer guiños y comparaciones con {referencias} SOLO como humor de cultura pop (ej. "se puso más intenso que concierto de Bad Bunny").
  NUNCA inventes frases, delitos, escándalos ni acusaciones atribuidas a personas reales; nada de apoyar o atacar partidos, candidatos o elecciones; nada de odio ni burlas por nacionalidad.
- Define UN estilo visual para todas las partes.

No repitas estas series anteriores: {historial}
{aprendizaje}

Devuelve SOLO JSON:
{{
  "serie": "título pegajoso de la serie en español",
  "elenco": [{{"fruta": "Mango", "nombre": "Don Mango", "personalidad": "galán presumido", "aspecto": "mango maduro con bigote y lentes de sol"}}],
  "estilo_visual": "una oración con el estilo visual común",
  "hashtags": ["#tag1", "#tag2"],
  "partes": [{{"titulo": "título de la parte", "enfoque": "qué pasa en esta parte, 1-2 oraciones"}}]
}}"""

PROMPT_PARTE = """Eres guionista de videos virales de TikTok para un canal sin rostro de novelas de frutas.
Público: {publico}. Idioma: {idioma}.

Serie: "{serie}" — esta es la PARTE {n} DE {total}.
Elenco fijo (úsalo igual en todas las partes): {elenco}
Esta parte: {titulo} — {enfoque}
Partes anteriores (para continuidad, no las repitas): {anteriores}
Adelanto de la siguiente parte: {siguiente}

Reglas:
- Exactamente {escenas} escenas. Narración total de AL MENOS {palabras} palabras (el video debe durar más de 1 minuto), unas 30 palabras por escena.
- La escena 1 empieza con "Parte {n}." y luego un gancho que detenga el scroll en menos de 14 palabras.{recap}
- Habla como un compa contando un chisme. TERMINA CADA ORACIÓN con una de estas muletillas, alternándolas: {muletillas}.
- Puedes hacer guiños de humor a {referencias} (comparaciones, referencias a canciones o frases famosas reales),
  pero NUNCA inventes frases, delitos o escándalos de personas reales, ni apoyes o ataques partidos o candidatos.
- {cierre}
- Para cada escena escribe un prompt de imagen EN INGLÉS con este estilo: {estilo}. Describe las frutas del elenco por su aspecto.
  Sin texto, letras ni logos en la imagen. NO dibujes personas reales ni sus caras: solo frutas.
- Para cada escena escribe también "busqueda": 2-4 palabras EN INGLÉS para buscar video de stock relacionado (ej. "mango fruit closeup").

Devuelve SOLO JSON:
{{
  "titulo": "descripción para TikTok, máx. 110 caracteres, con 1 emoji (sin el número de parte)",
  "resumen": "una oración con lo que pasó en esta parte",
  "escenas": [{{"narracion": "...", "imagen": "...", "busqueda": "..."}}]
}}"""


def _json(texto: str) -> dict:
    m = re.search(r"\{.*\}", texto.strip(), re.S)
    if not m:
        raise ValueError(f"Gemini no devolvió JSON: {texto[:300]}")
    return json.loads(m.group(0))


def _generar(client, modelo: str, prompt: str, intentos: int = 6):
    """Llama a Gemini reintentando si el modelo está saturado (503) o hay límite momentáneo (429)."""
    espera = 10
    for i in range(intentos):
        try:
            return client.models.generate_content(
                model=modelo, contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.9),
            )
        except Exception as e:
            txt = str(e)
            if i == intentos - 1 or not any(c in txt for c in ("503", "UNAVAILABLE", "429", "500", "overloaded")):
                raise
            print(f"  Gemini ocupado ({txt[:60]}...), reintento en {espera}s")
            time.sleep(espera)
            espera = min(espera * 2, 120)


def _pedir_json(client, modelo: str, prompt: str, validar) -> dict:
    for intento in range(3):
        r = _generar(client, modelo, prompt)
        try:
            d = _json(r.text)
            if validar(d):
                return d
            print(f"  respuesta incompleta (intento {intento + 1})")
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  JSON inválido (intento {intento + 1}): {e}")
    raise RuntimeError("Gemini no devolvió una respuesta válida")


def planear_serie(client: genai.Client, cfg: dict, tema: str | None, historial: list[str],
                  aprendizaje: str = "") -> dict:
    canal = cfg["canal"]
    partes = cfg["serie"]["partes"]
    tema = tema or f"elige una historia nueva, específica y muy chismosa dentro de: {canal['nicho']}"
    prompt = PROMPT_SERIE.format(
        nicho=canal["nicho"], publico=canal["publico"], idioma=canal["idioma"], partes=partes,
        referencias=canal.get("referencias", "famosos"),
        tema=tema, historial="; ".join(historial[-60:]) or "none", aprendizaje=aprendizaje,
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
        txt = "La última escena cierra toda la serie y dice: \"Sígueme para la próxima novela.\""
    else:
        txt = f"La última escena deja en suspenso la parte {n + 1} y dice: \"Sígueme para no perderte la parte {n + 1} mañana.\""
        if cta.get("comentar_parte"):
            txt += f" También pide que comenten \"PARTE {n + 1}\" si la quieren."
    if cta.get("apoyo"):
        txt += f" Termina con esta frase exacta: \"{cta['apoyo']}\""
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
        anteriores=" | ".join(plan["resumenes"]) or "ninguna (esta es la primera parte)",
        siguiente="ninguna — este es el final" if ultima else plan["partes"][n]["titulo"],
        escenas=v["escenas"], palabras=v["palabras_objetivo"], estilo=plan["estilo_visual"],
        recap="" if n == 1 else " La escena 1 puede conectar en pocas palabras con la parte anterior.",
        elenco=json.dumps(plan.get("elenco", []), ensure_ascii=False),
        muletillas=", ".join(f'"{m}"' for m in cfg["canal"].get("muletillas", [])) or "ninguna",
        referencias=cfg["canal"].get("referencias", "famosos"),
        cierre=_cierre(cfg, n, ultima),
    )
    minimo = int(v["palabras_objetivo"] * 0.9)
    palabras = lambda d: sum(len(e.get("narracion", "").split()) for e in d.get("escenas", []))
    g = _pedir_json(client, cfg["modelos"]["texto"], prompt,
                    lambda d: len(d.get("escenas", [])) >= 2 and palabras(d) >= minimo)
    g["escenas"] = g["escenas"][: v["escenas"]]
    g["titulo"] = f"{plan['serie']} — Parte {n}/{total}: {g['titulo']}"
    g["hashtags"] = plan.get("hashtags", [])
    g["tema"] = f"{plan['serie']} (parte {n}/{total})"
    g["parte"] = n
    return g
