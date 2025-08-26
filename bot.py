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

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [7710920544, 7560374352, 7837963996, 8465613365]  # Nuevo admin agregado

PEDIR_NOMBRE, PEDIR_TELEFONO, PEDIR_CORREO, PEDIR_ROL = range(4)
ESPERANDO_MENSAJE = "ESPERANDO_MENSAJE"

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
    app.run_polling()

if __name__ == "__main__":
    main()
