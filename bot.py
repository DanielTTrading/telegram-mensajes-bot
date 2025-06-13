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
ADMIN_IDS = [7710920544, 7560374352]

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

    await query.message.reply_text("Escribe el mensaje que deseas enviar (puedes incluir imagen o video).")
    return ESPERANDO_MENSAJE

async def enviar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = update.message.caption if update.message.caption else update.message.text
    rol = context.user_data.get("rol_destino")

    if rol == "todos":
        usuarios = obtener_usuarios_por_rol("Membresía Básica") + obtener_usuarios_por_rol("Membresía Platinum")
    else:
        usuarios = obtener_usuarios_por_rol(rol)

    enviados = 0

    # Imagen
    if update.message.photo:
        foto = update.message.photo[-1]
        archivo = await foto.get_file()
        os.makedirs("imagenes_temp", exist_ok=True)
        image_path = f"imagenes_temp/temp_{update.effective_user.id}.jpg"
        await archivo.download_to_drive(image_path)

        for user_id in usuarios:
            try:
                with open(image_path, "rb") as img:
                    await context.bot.send_photo(chat_id=user_id, photo=img, caption=mensaje)
                    enviados += 1
            except:
                pass
        os.remove(image_path)

    # Video
    elif update.message.video:
        video = update.message.video
        archivo = await video.get_file()
        os.makedirs("videos_temp", exist_ok=True)
        video_path = f"videos_temp/temp_{update.effective_user.id}.mp4"
        await archivo.download_to_drive(video_path)

        for user_id in usuarios:
            try:
                with open(video_path, "rb") as vid:
                    await context.bot.send_video(chat_id=user_id, video=vid, caption=mensaje)
                    enviados += 1
            except:
                pass
        os.remove(video_path)

    # Texto
    else:
        for user_id in usuarios:
            try:
                await context.bot.send_message(chat_id=user_id, text=mensaje)
                enviados += 1
            except:
                pass

    await update.message.reply_text(f"✅ Mensaje enviado a {enviados} usuario(s) del grupo '{rol}'")
    return ConversationHandler.END

async def listar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    basicos = obtener_usuarios_por_rol("Membresía Básica")
    platinum = obtener_usuarios_por_rol("Membresía Platinum")
    mensaje = (
        f"👥 *Resumen de usuarios:*\n\n"
        f"📩 Membresía Básica: {len(basicos)} usuarios\n"
        f"🏆 Membresía Platinum: {len(platinum)} usuarios"
    )
    await update.message.reply_text(mensaje, parse_mode="Markdown")

async def configurar_menu_completo(app: Application):
    comandos = [
        BotCommand("menu", "Enviar mensaje por membresía"),
        BotCommand("listar", "Listar usuarios registrados"),
        BotCommand("reset", "Reiniciar registro"),
    ]
    await app.bot.set_my_commands(comandos)
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
        states={ESPERANDO_MENSAJE: [MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO, enviar_mensaje)]},
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
