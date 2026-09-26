# MichiHub News Bot 🐾📰

Bot de Telegram que revisa noticias mundiales en tiempo real y las publica
en un canal como una **imagen** con el diseño de MichiHub (mismo logotipo,
colores y tipografía de la app), en vez de solo texto plano.

Corre automáticamente cada 15 minutos vía GitHub Actions — no necesitas
tener ninguna computadora prendida.

## Cómo configurarlo

### 1. Consigue tu API key gratuita de GNews

1. Entra a [gnews.io](https://gnews.io/) y crea una cuenta gratis (no pide tarjeta).
2. Copia la API key de tu panel — el plan gratuito da 100 peticiones al día,
   de sobra para revisar cada 15 minutos.

### 2. Agrega los 3 secretos en GitHub

En tu repositorio: **Settings → Secrets and variables → Actions → New repository secret**,
agrega estos tres:

| Nombre | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN` | El token de tu bot (te lo da @BotFather) |
| `TELEGRAM_CHAT_ID` | El @usuario o ID numérico de tu canal |
| `GNEWS_API_KEY` | La API key que copiaste de GNews |

Si ya tenías configurados `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` del bot
de sismos, no hace falta tocarlos — solo agrega el nuevo `GNEWS_API_KEY`.

### 3. Listo

El workflow `.github/workflows/check-news.yml` ya corre solo cada 15
minutos. También puedes probarlo manualmente desde la pestaña **Actions**
de GitHub → selecciona "Revisar noticias y avisar en Telegram" → **Run workflow**.

## Cómo funciona

1. Cada 15 minutos, `send_news.py` le pregunta a la API de GNews por las
   últimas noticias mundiales en español.
2. Compara contra `sent_news.json` para no repetir una noticia ya enviada.
3. Por cada noticia nueva, genera una imagen (usando el diseño de
   `assets/plantilla.html`, con el logo de MichiHub) con un navegador sin
   interfaz (Playwright).
4. Envía esa imagen al canal de Telegram configurado, con el titular y el
   link a la fuente en el pie de foto.

## Archivos

- `send_news.py` — el bot en sí.
- `assets/plantilla.html` — el diseño visual de la imagen (edítalo si quieres cambiar el look).
- `assets/logo.png` — el logotipo de MichiHub usado en la imagen.
- `sent_news.json` — registro de noticias ya enviadas (se actualiza solo).
- `.github/workflows/check-news.yml` — la automatización que lo corre cada 15 min.
