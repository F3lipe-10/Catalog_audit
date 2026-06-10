"""
================================================================================
SCRIPT DE MIGRACIÓN: JSON → SQL
================================================================================
Genera un archivo migracion.sql con todos los INSERT necesarios.
No requiere instalar ningún paquete extra.

USO:
    python migrar_a_sql.py                  # migración completa
    python migrar_a_sql.py --solo-categorias  # solo sube categorias.json

Luego abre Supabase → SQL Editor → pega el contenido de migracion.sql → Run.

Archivos migrados:
  - data/cache_carne.json  → tabla cache_carne
  - categorias.json        → tabla configuracion (clave='categorias')
================================================================================
"""

import json
import os
import sys


RUTA_SALIDA = "migracion.sql"
RUTA_SALIDA_CATS = "migracion_categorias.sql"


def _escapar(valor: str) -> str:
    """Escapa comillas simples para SQL estándar."""
    return valor.replace("'", "''")


def _generar_cache_carne(cache: dict) -> list[str]:
    lineas = []
    for producto, es_carne in cache.items():
        if not isinstance(producto, str) or not isinstance(es_carne, bool):
            continue
        prod_esc = _escapar(producto)
        val = "true" if es_carne else "false"
        lineas.append(
            f"INSERT INTO cache_carne (producto, es_carne) "
            f"VALUES ('{prod_esc}', {val}) "
            f"ON CONFLICT (producto) DO UPDATE SET es_carne = EXCLUDED.es_carne;"
        )
    return lineas


def main():
    bloques = []

    # ── Cabecera: crear tablas ──────────────────────────────────────────────
    bloques.append("""\
-- ============================================================
-- PASO 1: Crear tablas (seguro repetir, usa IF NOT EXISTS)
-- ============================================================
CREATE TABLE IF NOT EXISTS cache_carne (
    producto    TEXT PRIMARY KEY,
    es_carne    BOOLEAN NOT NULL,
    creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS configuracion (
    clave          TEXT PRIMARY KEY,
    valor          TEXT NOT NULL,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")

    # ── cache_carne.json ────────────────────────────────────────────────────
    ruta_cache = os.path.join(os.path.dirname(__file__), "data", "cache_carne.json")
    if os.path.exists(ruta_cache):
        with open(ruta_cache, "r", encoding="utf-8") as f:
            cache = json.load(f)
        lineas = _generar_cache_carne(cache)
        if lineas:
            bloques.append(f"""\
-- ============================================================
-- PASO 2: Migrar caché de carne ({len(lineas)} items)
-- ============================================================
""")
            bloques.append("\n".join(lineas))
            print(f"OK  cache_carne.json: {len(lineas)} items incluidos.")
        else:
            print("    cache_carne.json vacio o invalido, omitiendo.")
    else:
        print("    data/cache_carne.json no encontrado, omitiendo.")

    # ── categorias.json ─────────────────────────────────────────────────────
    ruta_cats = os.path.join(os.path.dirname(__file__), "categorias.json")
    if os.path.exists(ruta_cats):
        with open(ruta_cats, "r", encoding="utf-8") as f:
            cats = json.load(f)
        valor_esc = _escapar(json.dumps(cats, ensure_ascii=False))
        bloques.append(f"""\

-- ============================================================
-- PASO 3: Migrar categorias.json
-- ============================================================
INSERT INTO configuracion (clave, valor)
VALUES ('categorias', '{valor_esc}')
ON CONFLICT (clave)
DO UPDATE SET
    valor          = EXCLUDED.valor,
    actualizado_en = CURRENT_TIMESTAMP;
""")
        print("OK  categorias.json incluido.")
    else:
        print("    categorias.json no encontrado, omitiendo.")

    # ── Escribir archivo ────────────────────────────────────────────────────
    contenido = "\n".join(bloques)
    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        f.write(contenido)

    tam_kb = os.path.getsize(RUTA_SALIDA) / 1024
    print(f"\nArchivo generado: {RUTA_SALIDA} ({tam_kb:.1f} KB)")
    print()
    print("Proximos pasos:")
    print("  1. Abre https://supabase.com -> tu proyecto -> SQL Editor")
    print("  2. Copia el contenido de migracion.sql y pegalo ahi")
    print("  3. Haz clic en 'Run'")
    print("  4. Listo para hacer el deploy!")


def solo_categorias():
    ruta_cats = os.path.join(os.path.dirname(__file__), "categorias.json")
    if not os.path.exists(ruta_cats):
        print("ERROR: categorias.json no encontrado.")
        return
    with open(ruta_cats, "r", encoding="utf-8") as f:
        cats = json.load(f)
    valor_esc = _escapar(json.dumps(cats, ensure_ascii=False))
    contenido = f"""\
-- Actualizar categorias.json en Supabase
INSERT INTO configuracion (clave, valor)
VALUES ('categorias', '{valor_esc}')
ON CONFLICT (clave)
DO UPDATE SET
    valor          = EXCLUDED.valor,
    actualizado_en = CURRENT_TIMESTAMP;
"""
    with open(RUTA_SALIDA_CATS, "w", encoding="utf-8") as f:
        f.write(contenido)
    tam_kb = os.path.getsize(RUTA_SALIDA_CATS) / 1024
    print(f"Archivo generado: {RUTA_SALIDA_CATS} ({tam_kb:.1f} KB)")
    print("Pega el contenido en Supabase → SQL Editor → Run.")


if __name__ == "__main__":
    if "--solo-categorias" in sys.argv:
        solo_categorias()
    else:
        main()
