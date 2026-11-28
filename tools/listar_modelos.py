"""Lista los modelos de la API de Gemini disponibles para tu clave y qué métodos soportan."""
import os

import requests

r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                 params={"pageSize": 1000}, headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, timeout=60)
r.raise_for_status()
for m in r.json().get("models", []):
    metodos = ",".join(m.get("supportedGenerationMethods", []))
    nombre = m["name"].replace("models/", "")
    if any(k in nombre for k in ("veo", "video", "image", "flash", "imagen")) or "LongRunning" in metodos:
        print(f"{nombre:55} {metodos}")
