"""Paso único: autoriza tu cuenta de TikTok y obtiene el refresh token.

Uso (en tu PC):
    set TIKTOK_CLIENT_KEY=...      (Windows)  /  export TIKTOK_CLIENT_KEY=...  (Mac/Linux)
    set TIKTOK_CLIENT_SECRET=...
    set TIKTOK_REDIRECT_URI=https://TU-SITIO.vercel.app/callback.html
    python tools/obtener_token_tiktok.py
"""
import os
import secrets
import urllib.parse

import requests

key = os.environ["TIKTOK_CLIENT_KEY"]
secret = os.environ["TIKTOK_CLIENT_SECRET"]
redirect = os.environ["TIKTOK_REDIRECT_URI"]

url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
    "client_key": key,
    "scope": "user.info.basic,video.publish,video.upload,video.list",
    "response_type": "code",
    "redirect_uri": redirect,
    "state": secrets.token_urlsafe(16),
})
print("\n1) Abre este enlace, inicia sesión con la cuenta del canal y acepta:\n")
print(url)
codigo = input("\n2) Pega aquí el código que muestra la página: ").strip()
codigo = urllib.parse.unquote(codigo)

r = requests.post(
    "https://open.tiktokapis.com/v2/oauth/token/",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={"client_key": key, "client_secret": secret, "code": codigo,
          "grant_type": "authorization_code", "redirect_uri": redirect},
    timeout=30,
)
d = r.json()
if "refresh_token" not in d:
    raise SystemExit(f"Error: {d}")
print("\n✅ Listo. Guarda esto como secreto TIKTOK_REFRESH_TOKEN en GitHub:\n")
print(d["refresh_token"])
print(f"\n(open_id: {d.get('open_id')}, vence en {d.get('refresh_expires_in', 0) // 86400} días; "
      "el pipeline lo renueva solo)")
