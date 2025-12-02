import os
import imaplib
from dotenv import load_dotenv

# 1) Cargar variables desde .env (IMAP_HOST, IMAP_USER, IMAP_PASS)
load_dotenv()

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER")
IMAP_PASS = os.getenv("IMAP_PASS")

print("🔍 Probando conexión IMAP...")
print(f"HOST: {IMAP_HOST!r}")
print(f"USER: {IMAP_USER!r}")

if not IMAP_USER or not IMAP_PASS:
    print("❌ IMAP_USER o IMAP_PASS no están definidos. Revisa tu archivo .env o tus variables de entorno.")
    exit(1)

try:
    # 2) Conexión al servidor IMAP
    mail = imaplib.IMAP4_SSL(IMAP_HOST)
    print("✅ Conectado al servidor IMAP, intentando login...")

    # 3) Login con usuario y contraseña de aplicación
    mail.login(IMAP_USER, IMAP_PASS)
    print("✅ Login correcto.")

    # 4) Seleccionar INBOX
    status, data = mail.select("INBOX")
    if status == "OK":
        print("📬 INBOX seleccionada correctamente.")
        print(f"   Número de mensajes en INBOX: {data[0].decode('utf-8')}")
    else:
        print(f"⚠️ No se pudo seleccionar INBOX. Status: {status}, data: {data}")

    # 5) Cerrar sesión
    mail.close()
    mail.logout()
    print("✅ Conexión IMAP finalizada correctamente.")

except Exception as e:
    print("❌ Error al conectar IMAP o hacer login:")
    print(e)
