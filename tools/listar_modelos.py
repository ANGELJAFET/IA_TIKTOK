"""Muestra los modelos de Gemini disponibles para tu API key (por si cambian los nombres)."""
from google import genai

client = genai.Client()  # usa GEMINI_API_KEY
for m in client.models.list():
    nombre = m.name.replace("models/", "")
    if any(k in nombre for k in ("flash", "image", "imagen", "banana", "veo", "tts")):
        print(nombre)
