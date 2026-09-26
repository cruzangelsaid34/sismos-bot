"""
Revisa noticias mundiales en tiempo real (API de GNews) y envía a un canal
de Telegram cada noticia nueva como una IMAGEN con el diseño de MichiHub
(misma tipografía, colores y logotipo que la app), en vez de solo texto.

Pensado para correr cada 15 minutos vía GitHub Actions (cron). Para evitar
avisos duplicados, guarda los IDs de las noticias ya enviadas en
`sent_news.json`, que el workflow "commitea" de vuelta al repositorio tras
cada ejecución (ver .github/workflows/check-news.yml).

Fuente de datos: https://gnews.io/ (API de noticias, categoría "world").
El plan gratuito de GNews permite 100 peticiones al día — por eso el bot
corre cada 15 minutos (96 veces al día) y no más seguido.

Requiere tres variables de entorno (Secrets en GitHub):
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID   (@usuario del canal o chat_id numérico)
- GNEWS_API_KEY      (gratis en https://gnews.io/ , sin tarjeta)
"""

import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

GNEWS_URL = "https://gnews.io/api/v4/top-headlines"
GNEWS_PARAMS_BASE = {
    "category": "world",
    "lang": "es",
    "max": 5,
}

RAIZ = Path(__file__).parent
ESTADO_PATH = RAIZ / "sent_news.json"
LOGO_PATH = RAIZ / "assets" / "logo.png"
PLANTILLA_PATH = RAIZ / "assets" / "plantilla.html"

# Cuánto tiempo mantenemos un ID en el historial antes de olvidarlo
# (para que el archivo no crezca para siempre).
RETENCION_HORAS = 24


# ---------------------------------------------------------------------------
# Estado (para no repetir noticias ya enviadas)
# ---------------------------------------------------------------------------

def cargar_enviados() -> dict:
    if not ESTADO_PATH.exists():
        return {}
    try:
        return json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def guardar_enviados(enviados: dict):
    ESTADO_PATH.write_text(
        json.dumps(enviados, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def podar_antiguos(enviados: dict) -> dict:
    limite = datetime.now(timezone.utc) - timedelta(hours=RETENCION_HORAS)
    resultado = {}
    for nid, ts in enviados.items():
        try:
            if datetime.fromisoformat(ts) > limite:
                resultado[nid] = ts
        except ValueError:
            continue
    return resultado


def id_de_articulo(articulo: dict) -> str:
    url = articulo.get("url", "")
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Obtener noticias
# ---------------------------------------------------------------------------

def obtener_noticias(api_key: str) -> list:
    params = {**GNEWS_PARAMS_BASE, "apikey": api_key}
    resp = requests.get(GNEWS_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("articles", [])


# ---------------------------------------------------------------------------
# Generar la imagen con el diseño de MichiHub
# ---------------------------------------------------------------------------

def _texto_relativo(fecha_iso: str) -> str:
    try:
        fecha = datetime.fromisoformat(fecha_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return ""
    seg = (datetime.now(timezone.utc) - fecha).total_seconds()
    if seg < 60:
        return "justo ahora"
    if seg < 3600:
        return f"hace {int(seg // 60)} min"
    if seg < 86400:
        return f"hace {int(seg // 3600)} h"
    return f"hace {int(seg // 86400)} d"


def _escapar_html(texto: str) -> str:
    return (
        (texto or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def construir_html(articulo: dict, logo_b64: str) -> str:
    titulo = _escapar_html(articulo.get("title", "Noticia sin título"))
    descripcion = _escapar_html(articulo.get("description") or "")
    fuente = _escapar_html((articulo.get("source") or {}).get("name") or "Fuente desconocida")
    fecha_txt = _texto_relativo(articulo.get("publishedAt", ""))

    plantilla = PLANTILLA_PATH.read_text(encoding="utf-8")
    return (
        plantilla
        .replace("{{LOGO_B64}}", logo_b64)
        .replace("{{TITULO}}", titulo)
        .replace("{{DESCRIPCION}}", descripcion)
        .replace("{{FUENTE}}", fuente)
        .replace("{{FECHA}}", fecha_txt)
    )


def generar_imagen(articulo: dict, navegador) -> bytes:
    logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    html = construir_html(articulo, logo_b64)

    pagina = navegador.new_page(viewport={"width": 1080, "height": 1350})
    pagina.set_content(html, wait_until="load")
    try:
        pagina.wait_for_selector("body[data-listo='1']", timeout=5000)
    except Exception:
        pass  # si tarda demasiado, se toma la captura igual
    imagen_bytes = pagina.screenshot(type="png")
    pagina.close()
    return imagen_bytes


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def enviar_foto_telegram(token: str, chat_id: str, imagen_bytes: bytes, caption: str) -> bool:
    base = f"https://api.telegram.org/bot{token}"
    resp = requests.post(
        f"{base}/sendPhoto",
        data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "Markdown"},
        files={"photo": ("noticia.png", imagen_bytes, "image/png")},
        timeout=60,
    )
    if not resp.ok:
        print(f"⚠️ Error enviando foto: {resp.status_code} {resp.text}", file=sys.stderr)
        return False
    print("✅ Imagen enviada correctamente")
    return True


def formatear_caption(articulo: dict) -> str:
    titulo = articulo.get("title", "Noticia sin título")
    fuente = (articulo.get("source") or {}).get("name") or "Fuente desconocida"
    url = articulo.get("url", "")
    lineas = [
        f"🌍 *{titulo}*",
        "",
        f"📰 {fuente}",
    ]
    if url:
        lineas.append(f"🔗 [Leer más]({url})")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    gnews_key = os.environ.get("GNEWS_API_KEY")

    faltantes = [
        nombre
        for nombre, valor in (
            ("TELEGRAM_BOT_TOKEN", token),
            ("TELEGRAM_CHAT_ID", chat_id),
            ("GNEWS_API_KEY", gnews_key),
        )
        if not valor
    ]
    if faltantes:
        sys.exit(f"❌ Faltan variables de entorno: {', '.join(faltantes)}")

    enviados = podar_antiguos(cargar_enviados())

    try:
        articulos = obtener_noticias(gnews_key)
    except Exception as exc:
        sys.exit(f"❌ No se pudo consultar GNews: {exc}")

    nuevos = [a for a in articulos if id_de_articulo(a) not in enviados]
    # De la más antigua a la más reciente, para que el orden en el canal
    # tenga sentido cronológico.
    nuevos.sort(key=lambda a: a.get("publishedAt", ""))

    if not nuevos:
        print("Sin noticias nuevas desde la última revisión.")
        return

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        for articulo in nuevos:
            nid = id_de_articulo(articulo)
            try:
                imagen_bytes = generar_imagen(articulo, navegador)
                caption = formatear_caption(articulo)
                ok = enviar_foto_telegram(token, chat_id, imagen_bytes, caption)
                if ok:
                    enviados[nid] = datetime.now(timezone.utc).isoformat()
                    print(f"✅ Enviada: {nid} — {articulo.get('title')}")
                else:
                    print(f"❌ No se pudo enviar: {nid}", file=sys.stderr)
            except Exception:
                import traceback
                print(f"⚠️ Fallo generando/enviando la noticia {nid}:", file=sys.stderr)
                traceback.print_exc()
        navegador.close()

    guardar_enviados(enviados)


if __name__ == "__main__":
    main()
