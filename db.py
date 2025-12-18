import psycopg2
import os
import time

# Carga la URL de la base de datos desde las variables de entorno
DB_URL = os.getenv("DATABASE_URL")


def conectar(reintentos=5, espera=5):
    """
    Intenta conectar a PostgreSQL con reintentos.
    Evita que el bot se caiga si Railway duerme la DB.
    """
    for intento in range(reintentos):
        try:
            return psycopg2.connect(DB_URL)
        except psycopg2.OperationalError as e:
            print(f"⚠️ DB no disponible (intento {intento + 1}/{reintentos})")
            time.sleep(espera)
    raise psycopg2.OperationalError("❌ No se pudo conectar a la base de datos tras varios intentos.")


def crear_tabla():
    """
    Crea la tabla usuarios si no existe.
    NO tumba el bot si la DB está caída.
    """
    try:
        conn = conectar()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id_telegram BIGINT PRIMARY KEY,
                nombre TEXT,
                telefono TEXT,
                correo TEXT,
                rol TEXT
            )
        """)
        conn.commit()
        conn.close()
        print("✅ Tabla usuarios verificada/creada correctamente")
    except Exception as e:
        print(f"⚠️ No se pudo crear/verificar la tabla usuarios: {e}")


def guardar_usuario(id_telegram, nombre, telefono, correo, rol):
    """
    Inserta o actualiza un usuario.
    No tumba el bot si la DB falla.
    """
    try:
        conn = conectar()
        c = conn.cursor()
        c.execute("""
            INSERT INTO usuarios (id_telegram, nombre, telefono, correo, rol)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id_telegram) DO UPDATE SET
                nombre = EXCLUDED.nombre,
                telefono = EXCLUDED.telefono,
                correo = EXCLUDED.correo,
                rol = EXCLUDED.rol
        """, (id_telegram, nombre, telefono, correo, rol))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Error guardando usuario {id_telegram}: {e}")


def obtener_usuarios_por_rol(rol):
    """
    Devuelve una lista de IDs de Telegram según la membresía.
    Si la DB falla, devuelve lista vacía.
    """
    try:
        conn = conectar()
        c = conn.cursor()
        c.execute("SELECT id_telegram FROM usuarios WHERE rol = %s", (rol,))
        usuarios = [row[0] for row in c.fetchall()]
        conn.close()
        return usuarios
    except Exception as e:
        print(f"⚠️ Error obteniendo usuarios por rol '{rol}': {e}")
        return []
