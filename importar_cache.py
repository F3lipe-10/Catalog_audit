"""
================================================================================
SCRIPT DE IMPORTACIÓN INICIAL DEL CACHÉ DE CARNES
================================================================================
Lee un CSV con items de carne ya conocidos y los guarda en la base de datos
para que ia_carne.py los reconozca sin llamar a la IA.

Guarda cada línea del CSV TAL COMO VIENE, sin limpiar ni transformar.

USO:
    python importar_cache.py Book1.csv
    o
    python importar_cache.py                 (busca Book1.csv por defecto)

La URL de la BD se lee, en orden de prioridad:
  1. Variable de entorno DATABASE_URL
  2. .streamlit/secrets.toml → [connections.db] url
================================================================================
"""

import os
import sys


# ============================================================================
# Conexión directa con SQLAlchemy (sin Streamlit)
# ============================================================================

def _get_engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        try:
            import toml  # incluido por Streamlit
            secrets_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
            secrets = toml.load(secrets_path)
            url = secrets["connections"]["db"]["url"]
        except Exception as e:
            print(f"❌ No se encontró DATABASE_URL ni secrets.toml: {e}")
            print("   Configura la variable de entorno DATABASE_URL y vuelve a intentar.")
            sys.exit(1)

    from sqlalchemy import create_engine
    return create_engine(url)


def _inicializar_tabla(engine):
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS cache_carne (
                producto  TEXT PRIMARY KEY,
                es_carne  BOOLEAN NOT NULL,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))


def importar(ruta_csv: str = "Book1.csv"):
    """Importa items del CSV al caché en la base de datos."""
    if not os.path.exists(ruta_csv):
        print(f"❌ No encuentro el archivo {ruta_csv}")
        print(f"   Coloca el CSV en este directorio o pásalo como argumento:")
        print(f"   python importar_cache.py ruta/a/tu_archivo.csv")
        return

    with open(ruta_csv, "r", encoding="utf-8-sig") as f:
        lineas = f.readlines()

    print(f"📄 Procesando {len(lineas)} líneas de {ruta_csv}...")

    items_a_insertar = {}
    saltados = 0
    for linea in lineas:
        item = linea.strip().lstrip("﻿")
        if not item:
            saltados += 1
            continue
        items_a_insertar[item] = True

    if not items_a_insertar:
        print("⚠️ No se encontraron items válidos en el CSV.")
        return

    print(f"🔌 Conectando a la base de datos...")
    engine = _get_engine()
    _inicializar_tabla(engine)

    from sqlalchemy import text
    with engine.begin() as conn:
        # Contar cuántos ya existen
        rows = conn.execute(text(
            "SELECT COUNT(*) FROM cache_carne WHERE producto = ANY(:productos)"
        ), {"productos": list(items_a_insertar.keys())}).scalar()
        ya_existian = rows or 0

        conn.execute(
            text("""
                INSERT INTO cache_carne (producto, es_carne)
                VALUES (:producto, :es_carne)
                ON CONFLICT (producto) DO NOTHING
            """),
            [{"producto": k, "es_carne": v} for k, v in items_a_insertar.items()],
        )

    nuevos = len(items_a_insertar) - ya_existian

    # Contar total después de insertar
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM cache_carne")).scalar()

    print(f"\n✅ Listo. Resumen:")
    print(f"   Items nuevos agregados: {nuevos}")
    print(f"   Items que ya estaban:   {ya_existian}")
    print(f"   Líneas vacías saltadas: {saltados}")
    print(f"   Total en caché ahora:   {total}")
    print(f"\n🚀 Estos items NO se consultarán a la IA.")


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else "Book1.csv"
    importar(ruta)
