# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Streamlit web app for classifying food catalog items against Sodexo business rules across 12 divisions. It integrates with Excel-based workflows and uses AI (DeepSeek API) to detect meat products. Persistent data (meat cache and keyword config) is stored in PostgreSQL via Supabase.

## Running the App

```bash
# Install dependencies
pip install -r requirements.txt

# Configure secrets (copy template, fill in API keys, user credentials, and DB URL)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# Run the app
streamlit run app.py
```

No automated test suite. Validation is done manually through the Streamlit interface.

## Database Setup (Supabase / PostgreSQL)

The app uses two tables in PostgreSQL, created automatically on first run by `db.py`:

- `cache_carne` — `(producto TEXT PK, es_carne BOOLEAN)` — persistent meat classification cache
- `configuracion` — `(clave TEXT PK, valor TEXT)` — key/value store; `clave='categorias'` holds the serialized `categorias.json`

**First-time migration from JSON files:**

```bash
# Generate SQL from existing JSON files (outputs migracion.sql)
python migrar_a_sql.py

# Then run migracion.sql in the Supabase SQL Editor
```

**Connection string** goes in `.streamlit/secrets.toml` under `[connections.db]`:
```toml
[connections.db]
url = "postgresql://user:password@host:5432/dbname"
```

## Utility Scripts

```bash
# Generate bcrypt password hash for secrets.toml
python generar_hash.py

# Pre-populate meat detection cache from CSV (uses DB, not JSON)
python importar_cache.py Book1.csv

# Generate migracion.sql from existing data/cache_carne.json + categorias.json
python migrar_a_sql.py
```

## Architecture

**Data flow**: User uploads Catalog Excel + BOT Excel + EXP Excel + BOT Charcuterie Excel → column validation → classification rules applied → DeepSeek AI call for "Local" items → colored Excel report generated (with EXP mismatches flagged) → download.

| Module | Role |
|--------|------|
| `app.py` | Streamlit UI: login gate, 4-file upload (Catalog/BOT/EXP/BOT Charcuterie), processing trigger, 2-tab layout (Main Dashboard + Detailed Analysis), Summary by Person, filters, downloads |
| `clasificador.py` | Core rules engine — classification + supplier/division overrides + Initial Catalog whitelist |
| `ia_carne.py` | DeepSeek API wrapper with 5-step strategy (DB cache → obvious meat → obvious non-meat → session cache → API batch) |
| `utils.py` | Excel read/write, DataFrame processing, openpyxl cell coloring, EXP mismatch detection |
| `config.py` | Master config: column names, division lists, business rules, keyword lists, color codes, flower logic |
| `auth.py` | Streamlit-authenticator login using bcrypt hashes from `secrets.toml` |
| `db.py` | PostgreSQL/Supabase abstraction — table init, cache_carne CRUD, categorias load/save |
| `categorias.json` | Local copy of keyword dictionary (banned, non_contracted, ppi, exceptions); canonical source is now the DB |

## Classification Rules (Priority Order)

Rules are applied in sequence; first match wins and assigns "R" (restricted) or "E" (exposed):

0. **Keyword + supplier non-contracted** (`REGLAS_NON_CONTRACTED_POR_SUPPLIER`) → "R" all divisions, and exempt from the BOT Charcuterie exposure. Two modes: default ("strong") rules are evaluated first and beat every other rule (e.g. "CFA", 5 suppliers); rules flagged with `categorias_restringidas` are evaluated last and only convert items whose base category is in that list, leaving other categories (Banned/Local/Dairy/Bakery) untouched (e.g. "Panera", 11 suppliers, restricted to Initial Catalog + PPI). See `config.py` for the ID lists.
1. **Banned** → "R" all divisions (microgreens, alfalfa sprouts, etc.)
2. **Local + AI meat** → "R" all divisions (DeepSeek consulted)
3. **Local + not meat** → "E" all divisions
4. **Non-contracted** → "R" all divisions (frozen, organic, dairy, proteins, formats, flowers without "edible", etc.)
5. **PPI** (diced, sliced, shredded, etc.) → "E" all divisions
6. **Initial Catalog fallback** → checked against `data/whitelist_initial_catalog.json`; "E" auto-exposed divisions; BOT file determines others
7. **Invalid description** → flagged for manual review

After classification, three override layers apply in order:
- **`REGLAS_ESPECIFICAS_POR_DIVISION`** — keyword-triggered R/E overrides per division (e.g., "edible flower" forces SCHOOL SERVICES to "R")
- **`REGLAS_ESPECIFICAS_POR_SUPPLIER`** — supplier-triggered overrides (e.g., Daylight Foods restricted in all divisions except SCHOOL SERVICES)
- **`EXCEPCIONES_POR_SKU_SUPPLIER`** / **`EXCEPCIONES_POR_CATEGORIA_SUPPLIER`** — last-mile exceptions that force "E" for specific SKUs or categories of a supplier in specific divisions (e.g., Black River beef SKUs exposed in UNIVERSITIES)

**BOT Charcuterie file**: non-contracted items found in this file are exposed ("E") in all divisions except SCHOOL SERVICES.

**EXP file validation**: items listed in the EXP file must be "E"; any mismatch is flagged in red in the output.

Divisions split into `DIVISIONES_AUTO_EXPUESTAS` (always "E") and `DIVISIONES_REQUIEREN_BOT` (check BOT file). This split is validated at startup in `config.py`.

## Key Configuration

**`config.py`** is the primary customization point:
- `COL_*` — column name mappings if Excel files use different headers (includes `COL_EXP_SKU`, `COL_EXP_SUPPLIER_ID`, `COL_EXP_DIVISION` for the new EXP file)
- `SKIP_ROWS_*` — header rows to skip in each Excel file (Catalog, BOT, EXP, BOT Charcuterie)
- `DIVISIONES` — 12 divisions with aliases (`ALIASES_COLUMNAS`) for column name variations
- `DIVISIONES_AUTO_EXPUESTAS` (8) / `DIVISIONES_REQUIEREN_BOT` (4) — must be exhaustive and non-overlapping; validated at import
- `SUPPLIERS_DAIRY_GNG` — 30+ supplier IDs with explicit dairy/grab-and-go permissions
- `PALABRAS_DAIRY` / `PALABRAS_GRAB_AND_GO` — keyword lists for dairy and grab-and-go detection
- `PALABRAS_FLOR` / `PALABRAS_FLOR_EXCLUIDAS` — flower classification logic
- `REGLAS_ESPECIFICAS_POR_DIVISION` / `REGLAS_ESPECIFICAS_POR_SUPPLIER` / `EXCEPCIONES_POR_SKU_SUPPLIER` / `EXCEPCIONES_POR_CATEGORIA_SUPPLIER` — override and exception rules
- `REGLAS_NON_CONTRACTED_POR_SUPPLIER` — keyword + supplier list that forces Non-Contracted ("R" everywhere); strict whole-word match, applied before every other rule
- `RUTA_ASIGNACIONES` (`data/asignaciones.xlsx`) — maps Supplier IDs to assigned persons; drives the "Summary by Person" dashboard
- `COL_ASSIGN_*` — column names in the assignments file
- `COLOR_OK/ERROR/BLANK/INVALID` — hex colors for output Excel cells
- `DEEPSEEK_MODEL` / `PAUSA_ENTRE_LOTES` — AI model and batch delay

**`.streamlit/secrets.toml`** (never commit — in `.gitignore`):
- `[cookie]` — session cookie config
- `[credentials.usernames.*]` — bcrypt-hashed user credentials
- `[deepseek]` or `[groq]` — API key
- `[connections.db]` — PostgreSQL URL for Supabase (`url = "postgresql://..."`) used by `db.py`

## Initial Catalog Whitelist

`data/whitelist_initial_catalog.json` stores multi-word patterns loaded by `importar_glosario.py`. A product matches the whitelist if it contains **all** words of any pattern (order-insensitive, plural-aware). Patterns are indexed by their alphabetically smallest word ("anchor") for fast O(n) lookup. Missing or malformed file is silently ignored (empty whitelist).

## Word Matching Behavior

Keywords in `categorias.json` are matched case-insensitively with plural awareness. Two modes: exact word boundary (`\b`) for short terms, or substring match for words ≥10 characters. The `_excepciones_cuidado` list prevents false positives (e.g., "oyster mushroom" should not match meat keywords).

## AI Caching Strategy

DeepSeek calls are expensive. `ia_carne.py` uses five steps:
1. **PostgreSQL `cache_carne` table** (via `db.py`) — persistent cache across sessions and deployments
2. `PALABRAS_CARNE_OBVIAS` keyword list — classify as meat, skip API
3. `PALABRAS_NO_CARNE_OBVIAS` keyword list — classify as non-meat, skip API
4. In-memory dict (`_cache_carne_memoria`) — loaded from DB at startup, avoids repeated DB reads within a session
5. API batched in groups of 20 with results saved to DB immediately

Substring matching thresholds differ from `clasificador.py`: min word length 8 (vs. 10) and min keyword length 4 (vs. 5) to catch concatenated forms like "GROUNDBEEF".

Use `importar_cache.py` to pre-seed the cache from a CSV before first run in a new environment. The legacy `data/cache_carne.json` is no longer the source of truth; use `migrar_a_sql.py` to migrate it to the DB.

## Supplier ID Normalization

Supplier IDs can arrive as floats (e.g., `1118971.0`), strings with whitespace, or NaN. The codebase normalizes all of these consistently — always strip `.0`, strip whitespace, and coerce NaN to `""` when comparing.
