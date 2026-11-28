"""Envía por Gmail el video del día (adjunto) con la descripción lista para copiar.

Variables: GMAIL_USER, GMAIL_APP_PASSWORD, CORREO_DESTINO (opcional), ESTADO_JOB, URL_EJECUCION
"""
import json
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
usuario = os.environ.get("GMAIL_USER")
clave = os.environ.get("GMAIL_APP_PASSWORD")
if not usuario or not clave:
    print("Correo no configurado (faltan GMAIL_USER / GMAIL_APP_PASSWORD); no se envía.")
    sys.exit(0)

destino = os.environ.get("CORREO_DESTINO") or usuario
estado = os.environ.get("ESTADO_JOB", "success")
url = os.environ.get("URL_EJECUCION", "")

finales = sorted((RAIZ / "salida").glob("*/final.mp4"))
msg = EmailMessage()
msg["From"] = f"Fact Drop <{usuario}>"
msg["To"] = destino

if estado == "success" and finales:
    final = finales[-1]
    g = json.loads((final.parent / "guion.json").read_text(encoding="utf-8"))
    import yaml
    cfg_tags = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))["canal"]["hashtags_base"]
    tags = list(dict.fromkeys(g.get("hashtags", []) + cfg_tags))
    descripcion = f"{g['titulo']} {' '.join(tags)}"
    msg["Subject"] = f"🎬 Video listo: {g.get('tema', 'Fact Drop')}"
    msg.set_content(
        f"Tu video de hoy está listo (adjunto).\n\n"
        f"DESCRIPCIÓN PARA TIKTOK (cópiala):\n\n{descripcion}\n\n"
        f"Al publicar: activa 'Contenido generado por IA' en Más opciones.\n\n"
        f"Ejecución: {url}\n"
    )
    datos = final.read_bytes()
    if len(datos) < 24 * 1024 * 1024:
        msg.add_attachment(datos, maintype="video", subtype="mp4", filename=f"{g.get('tema','video')[:60]}.mp4")
    else:
        msg.set_content(msg.get_content() + "\n(El video pesa más de 24 MB: descárgalo desde la ejecución.)\n")
else:
    msg["Subject"] = "⚠️ Fact Drop: hoy no se pudo generar el video"
    msg.set_content(f"La ejecución de hoy falló. Revisa el detalle aquí:\n{url}\n")

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
    s.login(usuario, clave)
    s.send_message(msg)
print(f"Correo enviado a {destino}: {msg['Subject']}")
