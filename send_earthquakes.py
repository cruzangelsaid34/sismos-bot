"""
Revisa el feed global de sismos del USGS (Servicio Geológico de EE.UU.) y
envía a un canal de Telegram cualquier sismo nuevo que no se haya avisado
todavía, sin importar su magnitud.

Pensado para correr cada 5 minutos vía GitHub Actions (cron). Para evitar
avisos duplicados, guarda los IDs ya enviados en `sent_quakes.json`, que el
workflow se encarga de "commitear" de vuelta al repositorio tras cada
ejecución (ver .github/workflows/check-earthquakes.yml).

Fuente de datos: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
Cobertura: mundial. Actualiza el feed cada ~1 minuto.

Requiere dos variables de entorno (Secrets en GitHub):
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID   (@usuario del canal o chat_id numérico)
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# Feed "past hour, all magnitudes" — cualquier sismo del planeta, sin filtro
# de magnitud, de la última hora. Como el workflow corre cada 5 minutos,
# esta ventana de 1 hora da margen de sobra ante cualquier retraso de
# GitHub Actions o del propio feed del USGS.
USGS_FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"

ESTADO_PATH = Path(__file__).parent / "sent_quakes.json"

# Cuánto tiempo mantenemos un ID en el historial antes de olvidarlo
# (solo para que el archivo no crezca para siempre; de sobra para no
# duplicar avisos dado que solo miramos la última hora del feed).
RETENCION_HORAS = 6


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
    return {
        qid: ts
        for qid, ts in enviados.items()
        if datetime.fromisoformat(ts) > limite
    }


def obtener_sismos() -> list:
    resp = requests.get(USGS_FEED_URL, timeout=30)
    resp.raise_for_status()
    return resp.json().get("features", [])


def formatear_mensaje(feature: dict) -> str:
    props = feature["properties"]
    coords = feature["geometry"]["coordinates"]  # [lon, lat, profundidad_km]
    lon, lat, profundidad = coords[0], coords[1], coords[2]

    mag = props.get("mag")
    mag_txt = f"{mag:.1f}" if isinstance(mag, (int, float)) else "N/D"
    mag_tipo = props.get("magType", "")
    lugar = props.get("place", "Ubicación desconocida")
    url = props.get("url", "")
    tsunami = props.get("tsunami", 0)
    alerta = props.get("alert")

    tiempo_ms = props.get("time")
    if tiempo_ms:
        fecha = datetime.fromtimestamp(tiempo_ms / 1000, tz=timezone.utc)
        fecha_txt = fecha.strftime("%d/%m/%Y %H:%M:%S UTC")
    else:
        fecha_txt = "N/D"

    lineas = [
        "🌎 *Sismo detectado*",
        "",
        f"📍 {lugar}",
        f"🔢 Magnitud: *{mag_txt}* {mag_tipo}".strip(),
        f"📏 Profundidad: {profundidad:.1f} km",
        f"🕒 {fecha_txt}",
        f"🧭 Coordenadas: {lat:.3f}, {lon:.3f}",
    ]
    if tsunami:
        lineas.append("🌊 Alerta de posible tsunami asociada")
    if alerta:
        lineas.append(f"⚠️ Nivel de alerta USGS: {alerta}")
    if url:
        lineas.append(f"🔗 [Ver detalle en USGS]({url})")

    return "\n".join(lineas)


def enviar_telegram(token: str, chat_id: str, texto: str, lat: float, lon: float):
    base = f"https://api.telegram.org/bot{token}"

    resp = requests.post(
        f"{base}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )

    # --- DEBUG: mostrar siempre la respuesta completa de Telegram ---
    # Aunque resp.ok sea True, esto nos dice a qué chat llegó realmente
    # el mensaje (id numérico y, si es un canal/grupo con nombre, su título).
    try:
        data = resp.json()
    except ValueError:
        data = None

    print(f"🔎 DEBUG chat_id usado: {chat_id!r}")
    print(f"🔎 DEBUG status HTTP: {resp.status_code}")
    if data and data.get("ok"):
        chat_info = data.get("result", {}).get("chat", {})
        print(
            "🔎 DEBUG Telegram confirma envío a -> "
            f"id: {chat_info.get('id')}, "
            f"tipo: {chat_info.get('type')}, "
            f"título/usuario: {chat_info.get('title') or chat_info.get('username') or chat_info.get('first_name')}"
        )
    else:
        print(f"🔎 DEBUG respuesta cruda de Telegram: {resp.text}")
    # --- fin DEBUG ---

    if not resp.ok:
        print(f"⚠️ Error enviando mensaje: {resp.status_code} {resp.text}", file=sys.stderr)
        return False

    # Pin del sismo en el mapa de Telegram
    requests.post(
        f"{base}/sendLocation",
        data={"chat_id": chat_id, "latitude": lat, "longitude": lon},
        timeout=30,
    )
    return True


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        sys.exit("❌ Faltan TELEGRAM_BOT_TOKEN y/o TELEGRAM_CHAT_ID")

    enviados = podar_antiguos(cargar_enviados())
    sismos = obtener_sismos()

    nuevos = [f for f in sismos if f["id"] not in enviados]
    # Enviar del más antiguo al más reciente, para que el orden en el canal
    # tenga sentido cronológico.
    nuevos.sort(key=lambda f: f["properties"].get("time", 0))

    if not nuevos:
        print("Sin sismos nuevos desde la última revisión.")
        return

    for feature in nuevos:
        qid = feature["id"]
        lon, lat = feature["geometry"]["coordinates"][:2]
        mensaje = formatear_mensaje(feature)

        ok = enviar_telegram(token, chat_id, mensaje, lat, lon)
        if ok:
            enviados[qid] = datetime.now(timezone.utc).isoformat()
            print(f"✅ Enviado: {qid} — {feature['properties'].get('place')}")
        else:
            print(f"❌ No se pudo enviar: {qid}", file=sys.stderr)

    guardar_enviados(enviados)


if __name__ == "__main__":
    main()
