"""
================================================================================
MÓDULO DE BASE DE DATOS
================================================================================
Abstracción sobre la conexión a PostgreSQL (Supabase u otro proveedor).
Se configura en .streamlit/secrets.toml:

    [connections.db]
    url = "postgresql://user:password@host:5432/dbname"

Tablas gestionadas:
  - cache_carne    : caché persistente de resultados IA (producto → es_carne)
  - configuracion  : pares clave/valor; usa clave='categorias' para el JSON
                     de palabras clave.
================================================================================
"""

import json
import streamlit as st
from sqlalchemy import text


# ============================================================================
# CONEXIÓN
# ============================================================================

@st.cache_resource
def _get_conn():
    """Conexión única por proceso, gestionada por Streamlit."""
    return st.connection("db", type="sql")


# ============================================================================
# INICIALIZACIÓN DE TABLAS (idempotente)
# ============================================================================

def inicializar_tablas() -> None:
    """Crea las tablas si no existen. Seguro llamar varias veces."""
    conn = _get_conn()
    with conn.session as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS cache_carne (
                producto    TEXT PRIMARY KEY,
                es_carne    BOOLEAN NOT NULL,
                creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS configuracion (
                clave          TEXT PRIMARY KEY,
                valor          TEXT NOT NULL,
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS asignaciones (
                supplier_id    TEXT PRIMARY KEY,
                supplier_name  TEXT,
                assigned_to    TEXT
            )
        """))
        s.commit()


# ============================================================================
# CACHÉ DE CARNE
# ============================================================================

@st.cache_resource
def _cache_carne_memoria() -> dict:
    """
    Carga TODAS las entradas del caché desde la BD una sola vez por proceso.
    Devuelve el dict mutable que actúa como caché en memoria; las funciones
    guardar_lote / limpiar lo modifican en-place.
    """
    conn = _get_conn()
    try:
        inicializar_tablas()
        df = conn.query("SELECT producto, es_carne FROM cache_carne", ttl=0)
        return {row.producto: bool(row.es_carne) for row in df.itertuples(index=False)}
    except Exception as e:
        print(f"[db] error cargando cache_carne: {e}")
        return {}


def cargar_cache_carne() -> dict:
    """Devuelve el dict en memoria con todos los resultados conocidos."""
    return _cache_carne_memoria()


def guardar_lote_cache_carne(items: dict) -> bool:
    """
    Persiste un lote de resultados {producto: es_carne} en la BD y actualiza
    el caché en memoria. Usa upsert para no duplicar entradas.
    """
    if not items:
        return True
    conn = _get_conn()
    try:
        with conn.session as s:
            s.execute(
                text("""
                    INSERT INTO cache_carne (producto, es_carne)
                    VALUES (:producto, :es_carne)
                    ON CONFLICT (producto)
                    DO UPDATE SET es_carne = EXCLUDED.es_carne
                """),
                [{"producto": k, "es_carne": bool(v)} for k, v in items.items()],
            )
            s.commit()
        _cache_carne_memoria().update(items)
        return True
    except Exception as e:
        print(f"[db] error guardando lote cache_carne: {e}")
        return False


def limpiar_cache_carne() -> bool:
    """Borra todos los registros del caché en BD y limpia la copia en memoria."""
    conn = _get_conn()
    try:
        with conn.session as s:
            s.execute(text("DELETE FROM cache_carne"))
            s.commit()
        _cache_carne_memoria.clear()   # fuerza recarga en el próximo acceso
        return True
    except Exception as e:
        print(f"[db] error limpiando cache_carne: {e}")
        return False


def contar_cache_carne() -> int:
    """Número de items en el caché (O(1), usa la copia en memoria)."""
    return len(_cache_carne_memoria())


# ============================================================================
# CONFIGURACIÓN (categorias.json)
# ============================================================================

def cargar_categorias() -> dict:
    """
    Lee el JSON de categorías desde la BD.
    Devuelve {} si la clave no existe o hay error.
    """
    conn = _get_conn()
    try:
        inicializar_tablas()
        df = conn.query(
            "SELECT valor FROM configuracion WHERE clave = 'categorias'",
            ttl=0,
        )
        if df.empty:
            return {}
        return json.loads(df.iloc[0]["valor"])
    except Exception as e:
        print(f"[db] error cargando categorias: {e}")
        return {}


def cargar_asignaciones_db() -> list[dict]:
    """Devuelve todas las asignaciones como lista de dicts."""
    conn = _get_conn()
    try:
        inicializar_tablas()
        df = conn.query(
            "SELECT supplier_id, supplier_name, assigned_to FROM asignaciones",
            ttl=0,
        )
        return df.to_dict("records")
    except Exception as e:
        print(f"[db] error cargando asignaciones: {e}")
        return []


def guardar_asignaciones_db(filas: list[dict]) -> bool:
    """
    Reemplaza todas las asignaciones en la BD.
    Cada dict debe tener: supplier_id, supplier_name, assigned_to.
    """
    conn = _get_conn()
    try:
        with conn.session as s:
            s.execute(text("DELETE FROM asignaciones"))
            if filas:
                s.execute(
                    text("""
                        INSERT INTO asignaciones (supplier_id, supplier_name, assigned_to)
                        VALUES (:supplier_id, :supplier_name, :assigned_to)
                    """),
                    filas,
                )
            s.commit()
        return True
    except Exception as e:
        print(f"[db] error guardando asignaciones: {e}")
        return False


def guardar_categorias(data: dict) -> bool:
    """Persiste el dict de categorías en la BD (upsert)."""
    conn = _get_conn()
    try:
        with conn.session as s:
            s.execute(
                text("""
                    INSERT INTO configuracion (clave, valor)
                    VALUES ('categorias', :valor)
                    ON CONFLICT (clave)
                    DO UPDATE SET
                        valor          = EXCLUDED.valor,
                        actualizado_en = CURRENT_TIMESTAMP
                """),
                {"valor": json.dumps(data, ensure_ascii=False)},
            )
            s.commit()
        return True
    except Exception as e:
        print(f"[db] error guardando categorias: {e}")
        return False
