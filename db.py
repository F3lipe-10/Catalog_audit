"""
================================================================================
MÓDULO DE BASE DE DATOS
================================================================================
Abstracción sobre la conexión a PostgreSQL (Supabase u otro proveedor).
Se configura en .streamlit/secrets.toml:

    [connections.db]
    url = "postgresql://user:password@host:5432/dbname"

Tablas gestionadas:
  - cache_carne          : caché persistente de resultados IA (producto → es_carne)
  - configuracion        : pares clave/valor; usa clave='categorias' para el JSON
                            de palabras clave.
  - metricas_historicas  : snapshot de métricas (match rate) de cada corrida,
                            desglosado por división / persona / categoría, para
                            poder verlo como historial y gráfica de tendencia.
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
                assigned_to    TEXT,
                optimized      BOOLEAN DEFAULT TRUE
            )
        """))
        s.execute(text("""
            ALTER TABLE asignaciones
            ADD COLUMN IF NOT EXISTS optimized BOOLEAN DEFAULT TRUE
        """))
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS metricas_historicas (
                id          SERIAL PRIMARY KEY,
                run_id      TEXT NOT NULL,
                etiqueta    TEXT,
                fecha       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                dimension   TEXT NOT NULL,
                valor       TEXT NOT NULL,
                total       INTEGER,
                matches     INTEGER,
                errors      INTEGER,
                blanks      INTEGER,
                invalid     INTEGER,
                match_rate  NUMERIC
            )
        """))
        s.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_metricas_dim_valor
            ON metricas_historicas (dimension, valor, fecha)
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
            "SELECT supplier_id, supplier_name, assigned_to, COALESCE(optimized, TRUE) AS optimized FROM asignaciones",
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
                        INSERT INTO asignaciones (supplier_id, supplier_name, assigned_to, optimized)
                        VALUES (:supplier_id, :supplier_name, :assigned_to, :optimized)
                    """),
                    filas,
                )
            s.commit()
        return True
    except Exception as e:
        print(f"[db] error guardando asignaciones: {e}")
        return False


# ============================================================================
# HISTORIAL DE MÉTRICAS
# ============================================================================

def guardar_metricas_historicas(run_id: str, etiqueta: str, filas: list[dict]) -> bool:
    """
    Persiste un snapshot de métricas de una corrida. Cada fila debe tener:
    dimension ('overall'|'division'|'person'|'category'), valor, total,
    matches, errors, blanks, invalid, match_rate.
    """
    if not filas:
        return True
    conn = _get_conn()
    try:
        inicializar_tablas()
        with conn.session as s:
            s.execute(
                text("""
                    INSERT INTO metricas_historicas
                        (run_id, etiqueta, dimension, valor, total, matches, errors, blanks, invalid, match_rate)
                    VALUES
                        (:run_id, :etiqueta, :dimension, :valor, :total, :matches, :errors, :blanks, :invalid, :match_rate)
                """),
                [
                    {
                        "run_id": run_id,
                        "etiqueta": etiqueta,
                        "dimension": f["dimension"],
                        "valor": f["valor"],
                        "total": int(f["total"]),
                        "matches": int(f["matches"]),
                        "errors": int(f["errors"]),
                        "blanks": int(f["blanks"]),
                        "invalid": int(f["invalid"]),
                        "match_rate": float(f["match_rate"]),
                    }
                    for f in filas
                ],
            )
            s.commit()
        return True
    except Exception as e:
        print(f"[db] error guardando metricas_historicas: {e}")
        return False


def cargar_metricas_historicas() -> "pd.DataFrame":
    """Devuelve todo el historial de métricas como DataFrame, ordenado por fecha."""
    import pandas as pd
    conn = _get_conn()
    try:
        inicializar_tablas()
        df = conn.query(
            """
            SELECT run_id, etiqueta, fecha, dimension, valor,
                   total, matches, errors, blanks, invalid, match_rate
            FROM metricas_historicas
            ORDER BY fecha ASC
            """,
            ttl=0,
        )
        return df
    except Exception as e:
        print(f"[db] error cargando metricas_historicas: {e}")
        return pd.DataFrame()


def borrar_metricas_historicas() -> bool:
    """Borra todo el historial de métricas."""
    conn = _get_conn()
    try:
        with conn.session as s:
            s.execute(text("DELETE FROM metricas_historicas"))
            s.commit()
        return True
    except Exception as e:
        print(f"[db] error borrando metricas_historicas: {e}")
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
