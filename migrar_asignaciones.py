"""
================================================================================
SCRIPT DE MIGRACIÓN: asignaciones.xlsx → Supabase
================================================================================
Lee data/asignaciones.xlsx y sube todas las filas a la tabla `asignaciones`
en Supabase (reemplaza el contenido existente).

USO:
    python migrar_asignaciones.py

Requiere que .streamlit/secrets.toml tenga configurada [connections.db].
================================================================================
"""

import sys
import pandas as pd


RUTA_EXCEL = "data/asignaciones.xlsx"


def main():
    try:
        import streamlit as st
    except ImportError:
        print("ERROR: instala streamlit antes de ejecutar este script.")
        sys.exit(1)

    try:
        import config
        import db
    except ImportError as e:
        print(f"ERROR importando módulos del proyecto: {e}")
        sys.exit(1)

    # Leer Excel
    try:
        df = pd.read_excel(RUTA_EXCEL)
    except FileNotFoundError:
        print(f"ERROR: no se encontró '{RUTA_EXCEL}'")
        sys.exit(1)

    cols = [config.COL_ASSIGN_SUPPLIER_ID, config.COL_ASSIGN_SUPPLIER, config.COL_ASSIGN_PERSON]
    faltantes = [c for c in cols if c not in df.columns]
    if faltantes:
        print(f"ERROR: faltan columnas en el Excel: {', '.join(faltantes)}")
        sys.exit(1)

    df = df[cols].copy()
    df[config.COL_ASSIGN_SUPPLIER_ID] = (
        df[config.COL_ASSIGN_SUPPLIER_ID]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )
    df = df.dropna(subset=[config.COL_ASSIGN_SUPPLIER_ID])
    df = df[df[config.COL_ASSIGN_SUPPLIER_ID] != ""]

    filas = [
        {
            "supplier_id":   row[config.COL_ASSIGN_SUPPLIER_ID],
            "supplier_name": row[config.COL_ASSIGN_SUPPLIER] if pd.notna(row[config.COL_ASSIGN_SUPPLIER]) else "",
            "assigned_to":   row[config.COL_ASSIGN_PERSON] if pd.notna(row[config.COL_ASSIGN_PERSON]) else "",
        }
        for _, row in df.iterrows()
    ]

    print(f"Subiendo {len(filas)} asignaciones a Supabase...")
    ok = db.guardar_asignaciones_db(filas)
    if ok:
        print(f"OK  {len(filas)} asignaciones migradas correctamente.")
    else:
        print("ERROR: no se pudieron guardar las asignaciones. Revisa la conexión a Supabase.")
        sys.exit(1)


if __name__ == "__main__":
    main()
