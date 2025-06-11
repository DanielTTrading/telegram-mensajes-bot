import psycopg2
import os

# Carga la URL de la base de datos desde las variables de entorno
DB_URL = os.getenv("DATABASE_URL")


# Establecer conexión
def conectar():
    return psycopg2.connect(DB_URL)

# Crear tabla si no existe
def crear_tabla():
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

# Insertar o actualizar usuario
def guardar_usuario(id_telegram, nombre, telefono, correo, rol):
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

# Obtener IDs de usuarios por tipo de membresía
def obtener_usuarios_por_rol(rol):
    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT id_telegram FROM usuarios WHERE rol = %s", (rol,))
    usuarios = [row[0] for row in c.fetchall()]
    conn.close()
    return usuarios
