from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    MenuButtonCommands
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from db import crear_tabla, guardar_usuario, obtener_usuarios_por_rol
import asyncio
import os

# --- NUEVO ---
import imaplib
import email
from email.header import decode_header
import random
from datetime import datetime  # para la fecha de hoy en IMAP
import re
import html as html_lib

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [7710920544, 7560374352, 7837963996, 8465613365]  # Nuevo admin agregado

PEDIR_NOMBRE, PEDIR_TELEFONO, PEDIR_CORREO, PEDIR_ROL = range(4)
ESPERANDO_MENSAJE = "ESPERANDO_MENSAJE"

# --- NUEVO: configuración IMAP ---
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER")
IMAP_PASS = os.getenv("IMAP_PASS")
TRADINGVIEW_SENDER = "noreply@tradingview.com"  # solo referencial, usamos 'tradingview' en el From


# --- NUEVO: mapeo de ticker a nombre “bonito” ---
TICKER_NOMBRE = {
    "NVDA": "NVIDIA",
    "CORFICOLCF": "CORFICOLCF",
    # agrega aquí más tickers si quieres
}


def _decode_header_value(value):
    if not value:
        return ""
    decoded, charset = decode_header(value)[0]
    if isinstance(decoded, bytes):
        return decoded.decode(charset or "utf-8", errors="ignore")
    return decoded


def _html_to_text(html_content: str) -> str:
    """Convierte HTML sencillo en texto plano."""
    if not html_content:
        return ""
    # Reemplazar <br> y <p> por saltos de línea
    html_content = html_content.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    html_content = html_content.replace("</p>", "\n").replace("</div>", "\n")
    # Eliminar todas las etiquetas
    text = re.sub(r"<[^>]+>", "", html_content)
    # Decodificar entidades HTML
    text = html_lib.unescape(text)
    # Limpiar espacios
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _get_email_body(msg):
    """
    Intenta obtener primero 'text/plain'.
    Si no existe, toma 'text/html' y lo convierte a texto plano.
    """
    text_plain = None
    html_part = None

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")

            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain" and text_plain is None:
                payload = part.get_payload(decode=True)
                if payload:
                    text_plain = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")

            elif content_type == "text/html" and html_part is None:
                payload = part.get_payload(decode=True)
                if payload:
                    html_part = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            if content_type == "text/plain":
                text_plain = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
            elif content_type == "text/html":
                html_part = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")

    if text_plain:
        return text_plain.strip()
    if html_part:
        return _html_to_text(html_part)
    return ""


def _parse_tradingview_alert(body: str):
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    ticker = None
    price = None

    # 1) Español: "Se ha activado su alerta BTCUSD"
    for line in lines:
        if "Se ha activado su alerta" in line:
            parts = line.split()
            ticker = parts[-1].upper()
            break

    # 2) Inglés: "Your QLYS alert was triggered"
    if not ticker:
        for line in lines:
            low = line.lower()
            if "alert was triggered" in low:
                parts = line.split()
                if "alert" in parts:
                    idx = parts.index("alert")
                    if idx > 0:
                        ticker = parts[idx - 1].upper()
                        break

    # 3) Buscar precio en línea tipo:
    #    "QLYS Cruce descendente 81,45"
    #    "BTCUSD Cruce 91.999,00"
    #    "NVDA Crossing 172.67"
    if ticker:
        for line in lines:
            low = line.lower()
            if ticker in line and (
                "cruce" in low or
                "cross" in low or
                "crossing" in low
            ):
                tokens = line.split()
                for token in reversed(tokens):
                    limpio = token.strip(" ,:;()[]\"'")
                    if any(ch.isdigit() for ch in limpio):
                        price = limpio
                        break
                if price:
                    break

    return ticker, price


def _formatear_nombre_activo(ticker: str) -> str:
    if not ticker:
        return ""
    return TICKER_NOMBRE.get(ticker.upper(), ticker.upper())


# --- NUEVO: job que revisa el correo y envía mensaje a TODOS ---
async def revisar_correo_y_enviar(context: ContextTypes.DEFAULT_TYPE):
    try:
        if not (IMAP_USER and IMAP_PASS and IMAP_HOST):
            print("IMAP no configurado correctamente (IMAP_HOST/IMAP_USER/IMAP_PASS faltan).")
            return

        mail = imaplib.IMAP4_SSL(IMAP_HOST)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("INBOX")

        # Solo correos NO leídos del día de hoy
        today_str = datetime.utcnow().strftime("%d-%b-%Y")  # ej: "02-Dec-2025"
        print(f"[IMAP] Buscando correos UNSEEN SINCE {today_str}")
        status, data = mail.search(None, "UNSEEN", "SINCE", today_str)

        if status != "OK":
            print(f"[IMAP] Error en search UNSEEN SINCE: {status}, {data}")
            mail.close()
            mail.logout()
            return

        ids = data[0].split()
        print(f"[IMAP] Mensajes no leídos encontrados: {len(ids)}")

        if not ids:
            mail.close()
            mail.logout()
            return

        for msg_id in ids:
            # ⬇️ IMPORTANTE: usar BODY.PEEK[] para NO marcar como leído al hacer fetch
            status, msg_data = mail.fetch(msg_id, "(BODY.PEEK[])")
            if status != "OK":
                print(f"[IMAP] Error al hacer fetch de {msg_id}: {status}")
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = _decode_header_value(msg.get("Subject") or "")
            from_header = _decode_header_value(msg.get("From") or "")
            body = _get_email_body(msg)

            subject_lower = subject.lower()
            from_lower = from_header.lower()

            print(f"[IMAP] Revisando mensaje ID {msg_id.decode('utf-8')}:")
            print(f"       From: {from_header}")
            print(f"       Subject: {subject}")

            # Solo correos relacionados con TradingView
            if "tradingview" not in from_lower and "tradingview" not in subject_lower:
                print("       → No es correo de TradingView, se ignora (no se marca como leído).")
                # NO se marca como leído
                continue

            # Determinar tipo de alerta por el asunto
            if "stop loss" in subject_lower:
                tipo_alerta = "stop_loss"
            elif "profit" in subject_lower or "take profit" in subject_lower:
                tipo_alerta = "profit"
            else:
                print("       → Asunto no contiene stop loss ni profit, se ignora.")
                mail.store(msg_id, "+FLAGS", "\\Seen")
                continue

            # Extraer ticker y precio del cuerpo
            ticker, price = _parse_tradingview_alert(body)

            if not ticker or not price:
                print("       → No se pudo extraer ticker/precio del correo. Se ignora.")
                # También lo marcamos como leído para no repetirlo
                mail.store(msg_id, "+FLAGS", "\\Seen")
                continue

            nombre_activo = _formatear_nombre_activo(ticker)

            # Construir mensaje para los miembros
            if tipo_alerta == "stop_loss":
                texto_para_miembros = (
                    f"Atención🚨\n\n"
                    f"Estamos ejecutando stop loss en {nombre_activo} en {price}.\n\n"
                    f"Saludos.\n"
                    f"Equipo JP Tactical Trading."
                )
                tipo_texto = "Stop loss"
            else:  # profit
                porcentaje = random.choice([30, 40])
                texto_para_miembros = (
                    f"Atención🚨\n\n"
                    f"Estamos tomando utilidades en {nombre_activo}, cerrando en {porcentaje} %"
                    f"de la posición en {price}.\n\n"
                    f"Saludos.\n"
                    f"Equipo JP Tactical Trading."
                )
                tipo_texto = "Toma de utilidad"

            # Usuarios de TODOS (Básica + Platinum)
            usuarios = obtener_usuarios_por_rol("Membresía Básica") + obtener_usuarios_por_rol("Membresía Platinum")
            usuarios_unicos = list(dict.fromkeys(usuarios))  # quitar duplicados

            enviados = 0
            for uid in usuarios_unicos:
                try:
                    await context.bot.send_message(chat_id=uid, text=texto_para_miembros)
                    enviados += 1
                except Exception as e:
                    print(f"❌ Error al enviar mensaje TradingView a {uid}: {e}")

            print(
                f"✅ Alerta TradingView enviada a {enviados} usuario(s). "
                f"Tipo: {tipo_alerta}, ticker: {ticker}, precio: {price}"
            )

            # Resumen para administradores
            resumen_admin = (
                f"🔔 Alerta TradingView procesada\n\n"
                f"Tipo: {tipo_texto}\n"
                f"Activo: {nombre_activo} ({ticker})\n"
                f"Precio: {price}\n"
                f"Enviado a: {enviados} usuario(s)\n"
            )

            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=resumen_admin)
                except Exception as e:
                    print(f"❌ Error al enviar resumen a admin {admin_id}: {e}")

            # SOLO correos de TradingView que ya procesamos se marcan como leídos
            mail.store(msg_id, "+FLAGS", "\\Seen")

        mail.close()
        mail.logout()

    except Exception as e:
        print(f"Error en revisar_correo_y_enviar: {e}")


# ----------------------- TUS FUNCIONES ORIGINALES -----------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in ADMIN_IDS:
        await update.message.reply_text("Hola Admin. Usa /menu o /listar.")
        return ConversationHandler.END

    await update.message.reply_text("¡Hola! Bienvenido a JP Tactical Trading. Por favor, dime tu nombre completo.")
    return PEDIR_NOMBRE


async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nombre"] = update.message.text
    boton = [[KeyboardButton("Compartir mi número 📞", request_contact=True)]]
    await update.message.reply_text(
        "Ahora, por favor comparte tu número de teléfono:",
        reply_markup=ReplyKeyboardMarkup(boton, one_time_keyboard=True)
    )
    return PEDIR_TELEFONO


async def recibir_telefono(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contacto = update.message.contact
    if not contacto:
        await update.message.reply_text("Por favor usa el botón para compartir tu número.")
        return PEDIR_TELEFONO

    context.user_data["telefono"] = contacto.phone_number
    await update.message.reply_text("Perfecto. Ahora por favor escribe tu correo electrónico:")
    return PEDIR_CORREO


async def recibir_correo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["correo"] = update.message.text
    opciones = [["Membresía Básica"], ["Membresía Platinum"]]
    await update.message.reply_text(
        "¿Cuál es tu tipo de membresía?",
        reply_markup=ReplyKeyboardMarkup(opciones, one_time_keyboard=True, resize_keyboard=True)
    )
    return PEDIR_ROL


async def recibir_rol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rol = update.message.text
    nombre = context.user_data["nombre"]
    telefono = context.user_data["telefono"]
    correo = context.user_data["correo"]
    user_id = update.effective_user.id

    guardar_usuario(user_id, nombre, telefono, correo, rol)
    await update.message.reply_text(f"¡Gracias {nombre}! Quedaste registrado con la membresía '{rol}'.")
    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registro cancelado.")
    return ConversationHandler.END


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Has reiniciado el proceso. Usa /start para comenzar de nuevo.")
    return ConversationHandler.END


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    teclado = [
        [InlineKeyboardButton("📩 Membresía Básica", callback_data="basica")],
        [InlineKeyboardButton("🏆 Membresía Platinum", callback_data="platinum")],
        [InlineKeyboardButton("📤 Enviar a Todos", callback_data="todos")]
    ]
    await update.message.reply_text(
        "¿A qué grupo deseas enviar el mensaje?",
        reply_markup=InlineKeyboardMarkup(teclado)
    )


async def seleccionar_rol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        return

    context.user_data["rol_destino"] = {
        "basica": "Membresía Básica",
        "platinum": "Membresía Platinum",
        "todos": "todos"
    }.get(query.data)

    await query.message.reply_text("Escribe el mensaje que deseas enviar (puedes incluir imagen, video, PDF o audio).")
    return ESPERANDO_MENSAJE


async def enviar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = update.message.caption if update.message.caption else update.message.text
    rol = context.user_data.get("rol_destino")

    if rol == "todos":
        usuarios = obtener_usuarios_por_rol("Membresía Básica") + obtener_usuarios_por_rol("Membresía Platinum")
    else:
        usuarios = obtener_usuarios_por_rol(rol)

    enviados = 0

    def log_error(uid, e):
        print(f"❌ Error al enviar mensaje a {uid}: {e}")

    if update.message.photo:
        archivo = await update.message.photo[-1].get_file()
        path = f"imagenes_temp/{update.effective_user.id}.jpg"
        os.makedirs("imagenes_temp", exist_ok=True)
        await archivo.download_to_drive(path)
        for uid in usuarios:
            try:
                with open(path, "rb") as f:
                    await context.bot.send_photo(chat_id=uid, photo=f, caption=mensaje)
                    enviados += 1
            except Exception as e:
                log_error(uid, e)
        os.remove(path)

    elif update.message.video:
        archivo = await update.message.video.get_file()
        path = f"videos_temp/{update.effective_user.id}.mp4"
        os.makedirs("videos_temp", exist_ok=True)
        await archivo.download_to_drive(path)
        for uid in usuarios:
            try:
                with open(path, "rb") as f:
                    await context.bot.send_video(chat_id=uid, video=f, caption=mensaje)
                    enviados += 1
            except Exception as e:
                log_error(uid, e)
        os.remove(path)

    elif update.message.document and update.message.document.mime_type == "application/pdf":
        archivo = await update.message.document.get_file()
        path = f"docs_temp/{update.effective_user.id}.pdf"
        os.makedirs("docs_temp", exist_ok=True)
        await archivo.download_to_drive(path)
        for uid in usuarios:
            try:
                with open(path, "rb") as f:
                    await context.bot.send_document(chat_id=uid, document=f, caption=mensaje)
                    enviados += 1
            except Exception as e:
                log_error(uid, e)
        os.remove(path)

    elif update.message.voice:
        archivo = await update.message.voice.get_file()
        path = f"voice_temp/{update.effective_user.id}.ogg"
        os.makedirs("voice_temp", exist_ok=True)
        await archivo.download_to_drive(path)
        for uid in usuarios:
            try:
                with open(path, "rb") as f:
                    await context.bot.send_voice(chat_id=uid, voice=f, caption=mensaje)
                    enviados += 1
            except Exception as e:
                log_error(uid, e)
        os.remove(path)

    elif update.message.audio:
        archivo = await update.message.audio.get_file()
        path = f"audio_temp/{update.effective_user.id}.mp3"
        os.makedirs("audio_temp", exist_ok=True)
        await archivo.download_to_drive(path)
        for uid in usuarios:
            try:
                with open(path, "rb") as f:
                    await context.bot.send_audio(chat_id=uid, audio=f, caption=mensaje)
                    enviados += 1
            except Exception as e:
                log_error(uid, e)
        os.remove(path)

    else:
        for uid in usuarios:
            try:
                await context.bot.send_message(chat_id=uid, text=mensaje)
                enviados += 1
            except Exception as e:
                log_error(uid, e)

    await update.message.reply_text(f"✅ Mensaje enviado a {enviados} usuario(s) del grupo '{rol}'")
    return ConversationHandler.END


async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    b = obtener_usuarios_por_rol("Membresía Básica")
    p = obtener_usuarios_por_rol("Membresía Platinum")
    msg = f"👥 *Resumen de usuarios:*\n\n📩 Membresía Básica: {len(b)} usuarios\n🏆 Membresía Platinum: {len(p)} usuarios"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def configurar_menu_completo(app: Application):
    cmds = [
        BotCommand("menu", "Enviar mensaje por membresía"),
        BotCommand("listar", "Listar usuarios registrados"),
        BotCommand("reset", "Reiniciar registro"),
    ]
    await app.bot.set_my_commands(cmds)
    await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


def main():
    crear_tabla()
    app = Application.builder().token(TOKEN).build()

    registro = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PEDIR_NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
            PEDIR_TELEFONO: [MessageHandler(filters.CONTACT, recibir_telefono)],
            PEDIR_CORREO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_correo)],
            PEDIR_ROL: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_rol)],
        },
        fallbacks=[
            CommandHandler("cancelar", cancelar),
            CommandHandler("reset", reset)
        ],
    )

    envio = ConversationHandler(
        entry_points=[CallbackQueryHandler(seleccionar_rol)],
        states={
            ESPERANDO_MENSAJE: [MessageHandler(
                filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.VOICE | filters.AUDIO,
                enviar_mensaje
            )]
        },
        fallbacks=[],
    )

    app.add_handler(registro)
    app.add_handler(envio)
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("listar", listar))
    app.add_handler(CommandHandler("reset", reset))

    print("Bot corriendo...")

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(configurar_menu_completo(app))

    # Programar el job que revisa el correo cada 10 segundos
    job_queue = app.job_queue
    job_queue.run_repeating(revisar_correo_y_enviar, interval=10, first=10)

    app.run_polling()


if __name__ == "__main__":
    main()
