# TikTok IA automático 🎬

Genera y publica TikToks de datos curiosos en inglés (público de EE. UU.) todos los días, sin intervención.

**Flujo:** tema → guion (Gemini) → 5 imágenes IA (Gemini) → voz (edge-tts, gratis) → montaje con movimiento, subtítulos y música (FFmpeg) → TikTok (API oficial).
**Programador:** GitHub Actions (gratis), todos los días a las 7:47 pm hora del Este de EE. UU. (6:47 pm Honduras).
**Costo:** ≈ $0.17 por video → ≈ $5 al mes con 1 video diario.

---

## Paso 1 — Cuenta de TikTok
1. Crea una cuenta **personal** con un correo nuevo y la app en inglés.
2. Nombre, bio y foto en inglés y del nicho.
3. Durante 3–5 días mira y dale like a videos de datos curiosos en inglés.

## Paso 2 — Subir el proyecto a GitHub
1. Crea un repositorio **privado**, por ejemplo `tiktok-ia`.
2. Sube todo el contenido de esta carpeta, incluida la carpeta oculta `.github/`.

## Paso 3 — Sitio web para la app de TikTok (Vercel)
TikTok exige un sitio web, una política de privacidad y unos términos.
1. En `docs/*.html` cambia `CONTACT_EMAIL` por tu correo y, si quieres, el nombre "Daily Facts Studio".
2. En Vercel: **Add New → Project →** el mismo repo, con **Root Directory = `docs`**. Haz el deploy.
3. Te queda una dirección como `https://tiktok-ia-xxx.vercel.app`. Ahí estarán `/privacy.html`, `/terms.html` y `/callback.html`.

## Paso 4 — App de desarrollador de TikTok
1. Entra a **developers.tiktok.com** con la cuenta del canal → **Manage apps → Connect an app**.
2. Llena: nombre, ícono, categoría y las URLs de Terms, Privacy y Website del Paso 3.
3. **Add products:** *Login Kit* y *Content Posting API* (activa **Direct Post**).
4. **Scopes:** `user.info.basic`, `video.publish`, `video.upload`, `video.list` (este último para leer tus estadísticas).
5. **Redirect URI** (Login Kit → Web): `https://TU-SITIO.vercel.app/callback.html`
6. Copia el **Client key** y el **Client secret**.
7. En **Sandbox**, agrega la cuenta del canal como *target user* para poder probar ya.

## Paso 5 — Obtener el token (una sola vez, en tu PC)
```bash
pip install requests
# Windows (cmd):  set VAR=valor   |  Mac/Linux:  export VAR=valor
set TIKTOK_CLIENT_KEY=...
set TIKTOK_CLIENT_SECRET=...
set TIKTOK_REDIRECT_URI=https://TU-SITIO.vercel.app/callback.html
python tools/obtener_token_tiktok.py
```
Abre el enlace que imprime, acepta, copia el código que muestra la página y pégalo. Te da el **refresh token**.

## Paso 5b — Pexels (gratis)
1. Crea una cuenta en **pexels.com** y entra a **pexels.com/api** → *Your API Key*.
2. Guárdala en GitHub como secreto `PEXELS_API_KEY`.
Con `visuales: "pexels"` en `config.yaml` todo el pipeline es gratis.

## Paso 6 — 💳 (Opcional, más adelante) Imágenes IA con Gemini
1. Entra a **aistudio.google.com → Get API key → Create API key**.
2. **Set up billing**: vincula tu tarjeta y carga **$10**, que alcanzan para unos 50 videos.
3. Pon un **límite de gasto mensual de $10** en el proyecto.

## Paso 7 — Secretos en GitHub
En el repo: **Settings → Secrets and variables → Actions → New repository secret**:

| Nombre | Valor |
|---|---|
| `GEMINI_API_KEY` | la clave del Paso 6 |
| `TIKTOK_CLIENT_KEY` | Client key del Paso 4 |
| `TIKTOK_CLIENT_SECRET` | Client secret del Paso 4 |
| `TIKTOK_REFRESH_TOKEN` | el token del Paso 5 |
| `GH_PAT` | *(recomendado)* un token de GitHub *fine-grained* con permiso **Secrets: Read and write** sobre este repo, para que el token de TikTok se renueve solo |

## Paso 8 — Probar
**Actions → Publicar TikTok → Run workflow** con "Solo generar" marcado. A los ~5 min descarga el video en *Artifacts* y revísalo.
Si te gusta, corre de nuevo **sin** marcar la casilla: se sube a TikTok.

## Paso 9 — Auditoría de TikTok (para que sea público)
Hasta que TikTok audite tu app, **los videos se publican en privado** (solo tú los ves) y la cuenta debe estar en privado.
En el portal de la app pide la auditoría de *Content Posting API*. Suelen pedir un video demostrando el flujo: graba la ejecución en Actions y el resultado en TikTok.
Cuando la aprueben, en `config.yaml` cambia `privacidad: "PUBLIC_TO_EVERYONE"`.

> Mientras tanto puedes usar `modo: "borrador"`: el video llega a tu bandeja de TikTok y tú lo publicas con un toque. Así también agregas un sonido en tendencia.

---

## Cómo revisas cada video antes de publicarlo
Con `modo: "borrador"` (configuración actual) cada video llega a tu **bandeja de TikTok** como borrador:
1. TikTok te manda una notificación. Abres el borrador y ves el video completo.
2. Si te gusta: pega la descripción (la encuentras en GitHub → Actions → la ejecución del día), activa **"AI-generated content"**, puedes agregar un sonido en tendencia y publica.
3. Si no te gusta: lo descartas y la serie sigue igual al día siguiente.
Cuando confíes en la calidad, cambia a `modo: "directo"` y se publica solo.

## Cómo aprende qué le gusta a tu público
Antes de empezar cada serie nueva, el pipeline lee las vistas, likes, comentarios y compartidos de tus videos,
los agrupa por serie y le dice a la IA cuáles funcionaron mejor y peor para que la siguiente serie se parezca a las ganadoras.
El ranking queda en `data/rendimiento.json`. Necesita el permiso `video.list` en tu app de TikTok.

## Personalizar
- **Nicho, voz, número de escenas:** `config.yaml`
- **Cola de temas:** `data/temas.txt`, uno por línea. Si está vacía, la IA inventa el tema sin repetir los anteriores.
- **Música:** mp3 sin copyright en `assets/musica/`
- **Horario / más videos al día:** el `cron` en `.github/workflows/publicar.yml` (está en hora UTC)
- **Historial de lo publicado:** `data/historial.json`

## Problemas comunes
- **Error de modelo no encontrado:** Google cambió los nombres. Corre `python tools/listar_modelos.py` y actualiza `modelos` en `config.yaml`.
- **`unaudited_client_can_only_post_to_private_accounts`:** pon la cuenta de TikTok en privado hasta pasar la auditoría.
- **Falla la voz:** edge-tts es un servicio gratuito no oficial. Si deja de funcionar, se puede cambiar al TTS de Gemini (≈ $0.002 por video).
