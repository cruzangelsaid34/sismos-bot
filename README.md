# Alertas de sismos → Telegram (cualquier magnitud, mundial)

Avisa en tu canal de Telegram cada vez que ocurre un sismo en cualquier
parte del mundo, sin importar la magnitud, usando el feed público y
gratuito del USGS (Servicio Geológico de EE. UU.).

## ⚠️ Importante: qué tan "en tiempo real" es esto

GitHub Actions gratis no permite ejecutar algo verdaderamente instantáneo
las 24 horas. Este bot corre **cada 5 minutos** (el mínimo práctico), y
ocasionalmente GitHub puede retrasar unos minutos más la ejecución si hay
mucha carga en sus servidores. En la práctica vas a recibir el aviso
dentro de los primeros 5-10 minutos después de ocurrido el sismo, no al
instante. Para algo 100% instantáneo se necesitaría un servidor propio
corriendo permanentemente (tiene costo).

## Cómo configurarlo

### 1. Sube esta carpeta a un repositorio de GitHub
Incluye `send_earthquakes.py`, `requirements.txt`, `sent_quakes.json` y la
carpeta `.github/`.

### 2. Agrega el bot como administrador de tu canal
Tu canal → Administradores → Agregar administrador → tu bot → permiso de
"Publicar mensajes".

### 3. Obtén el `chat_id` del canal
- Canal público: `@tunombredecanal`.
- Canal privado: reenvía un mensaje del canal a
  [@userinfobot](https://t.me/userinfobot) para obtener el ID numérico.

### 4. Configura los Secrets en GitHub
Repositorio → **Settings → Secrets and variables → Actions → New repository
secret**:

| Nombre                | Valor                                    |
|------------------------|-------------------------------------------|
| `TELEGRAM_BOT_TOKEN`   | El token de tu bot (dado por @BotFather) |
| `TELEGRAM_CHAT_ID`     | El @usuario o ID numérico del canal      |

⚠️ Si ya compartiste un token en algún chat, **revócalo primero** con
@BotFather (`/mybots` → tu bot → API Token → Revoke) y usa el nuevo token
solo como Secret.

### 5. Habilita permisos de escritura para Actions
El bot necesita poder guardar `sent_quakes.json` de vuelta al repo (para no
enviar el mismo sismo dos veces). Ve a **Settings → Actions → General →
Workflow permissions** y selecciona **"Read and write permissions"**.

### 6. Pruébalo
Pestaña **Actions** → "Revisar sismos y avisar en Telegram" →
**Run workflow**.

## Cómo funciona

1. Cada 5 minutos, descarga el feed
   `all_hour.geojson` del USGS: todos los sismos del planeta —
   cualquier magnitud, incluso las negativas — de la última hora.
2. Compara cada sismo contra `sent_quakes.json` (los IDs ya avisados) para
   no duplicar mensajes.
3. Envía un mensaje de texto por cada sismo nuevo, con magnitud,
   profundidad, ubicación, hora UTC y enlace al detalle en USGS, más un pin
   de ubicación en el mapa de Telegram, y además un mensaje de **voz**
   (audio generado automáticamente con gTTS) leyendo la magnitud, el lugar
   y la profundidad. Si la generación o el envío de la voz falla (por
   ejemplo por un límite temporal de Google), el sismo igual queda
   marcado como avisado gracias al mensaje de texto, y no se reintenta el
   audio.
4. Guarda los nuevos IDs en `sent_quakes.json` y el propio workflow hace
   commit y push del archivo actualizado, para que la próxima ejecución
   sepa qué ya se avisó. Los registros de más de 6 horas se eliminan
   automáticamente para que el archivo no crezca sin control.

## Ajustar el filtro (opcional)
Si en algún momento quieres limitar por magnitud mínima en vez de recibir
absolutamente todos los sismos (incluyendo los muy pequeños, que pueden ser
bastante frecuentes), cambia en `send_earthquakes.py` la URL
`USGS_FEED_URL` por una de estas variantes:
- `.../summary/2.5_hour.geojson` → solo magnitud 2.5+
- `.../summary/4.5_hour.geojson` → solo magnitud 4.5+
- `.../summary/significant_hour.geojson` → solo sismos "significativos"
