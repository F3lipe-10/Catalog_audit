# Clasificador de Catálogo

Aplicación Streamlit que clasifica artículos de un catálogo de alimentos según reglas de negocio de Sodexo para 12 divisiones. Integra flujos de trabajo basados en Excel y usa IA (DeepSeek API) para detectar productos cárnicos. Los datos persistentes (caché de carne y configuración de palabras clave) se almacenan en PostgreSQL vía Supabase.

## Estructura

```
proyecto_catalogo/
├── app.py                         # UI Streamlit: login, carga de 4 archivos, procesamiento, 2 pestañas
├── auth.py                        # Login con streamlit-authenticator (bcrypt)
├── clasificador.py                # Motor de reglas: clasificación + overrides de supplier/división
├── ia_carne.py                    # Cliente DeepSeek con estrategia de 5 pasos y caché
├── utils.py                       # Lectura/escritura Excel, coloreado con openpyxl, detección EXP
├── config.py                      # Configuración maestra: columnas, divisiones, reglas, colores
├── db.py                          # Abstracción PostgreSQL/Supabase: CRUD de cache_carne y categorias
├── categorias.json                # Copia local del diccionario de palabras clave (fuente canon: DB)
├── generar_hash.py                # Genera hash bcrypt para secrets.toml
├── importar_cache.py              # Pre-pobla caché de carne desde CSV
├── importar_glosario.py           # Carga patrones al whitelist del catálogo inicial
├── migrar_a_sql.py                # Genera migracion.sql desde JSON locales
├── requirements.txt
├── data/
│   ├── asignaciones.xlsx          # Supplier ID → persona encargada (dashboard "Summary by Person")
│   └── whitelist_initial_catalog.json  # Patrones multi-palabra del catálogo inicial
├── .streamlit/
│   ├── secrets.toml               # Credenciales y API keys (NO subir a git)
│   └── secrets.toml.example
├── .gitignore
└── README.md
```

## Instalación local

1. **Crear entorno virtual:**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Mac/Linux
   source venv/bin/activate
   ```

2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurar secrets:**
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   # Edita secrets.toml con tus API keys, credenciales y URL de DB
   ```

4. **Generar hash de contraseña:**
   ```bash
   python generar_hash.py
   # Pega el hash en secrets.toml bajo [credentials.usernames.USUARIO]
   ```

5. **Configurar la base de datos (Supabase):**
   - Agrega la URL de conexión en `secrets.toml` bajo `[connections.db]`:
     ```toml
     [connections.db]
     url = "postgresql://user:password@host:5432/dbname"
     ```
   - Las tablas se crean automáticamente en el primer arranque.
   - Para migrar datos desde JSON existentes:
     ```bash
     python migrar_a_sql.py   # genera migracion.sql
     # Ejecuta migracion.sql en el Editor SQL de Supabase
     ```

6. **Ejecutar la app:**
   ```bash
   streamlit run app.py
   ```

## Base de datos (Supabase / PostgreSQL)

Dos tablas administradas por `db.py`:

| Tabla | Esquema | Uso |
|-------|---------|-----|
| `cache_carne` | `(producto TEXT PK, es_carne BOOLEAN)` | Caché persistente de clasificación de carne |
| `configuracion` | `(clave TEXT PK, valor TEXT)` | `clave='categorias'` guarda el diccionario serializado |

Para pre-poblar la caché desde un CSV antes del primer uso:
```bash
python importar_cache.py Book1.csv
```

## Flujo de datos

El usuario sube 4 archivos Excel → validación de columnas → reglas de clasificación → consulta IA para ítems "Local" → reporte Excel coloreado con discrepancias EXP marcadas en rojo → descarga.

| Archivo | Descripción |
|---------|-------------|
| Catalog | Catálogo principal de productos |
| BOT | Archivo de órdenes (determina exposición en divisiones BOT) |
| EXP | Archivo de exposición; discrepancias se marcan en rojo |
| BOT Charcuterie | Ítems non-contracted expuestos en divisiones excepto SCHOOL SERVICES |

## Reglas de clasificación (orden de prioridad)

1. **Banned** → R en todas las divisiones
2. **Local + es carne** (consulta DeepSeek) → R en todas
3. **Local + no es carne** → E en todas
4. **Non-contracted** → R en todas
5. **PPI** (cortado, rebanado, rallado, etc.) → E en todas
6. **Initial Catalog** → whitelist multi-palabra; E automático en divisiones auto-expuestas; BOT determina el resto
7. **Descripción inválida** → marcado para revisión manual

Después de clasificar se aplican tres capas de overrides (en orden):
- `REGLAS_ESPECIFICAS_POR_DIVISION` — overrides R/E por palabra clave y división
- `REGLAS_ESPECIFICAS_POR_SUPPLIER` — overrides R/E por proveedor
- `EXCEPCIONES_POR_SKU_SUPPLIER` / `EXCEPCIONES_POR_CATEGORIA_SUPPLIER` — excepciones de último paso que fuerzan E para SKUs o categorías específicas de un proveedor en divisiones específicas

## Divisiones

12 divisiones divididas en dos grupos:

- **Auto-expuestas** (siempre E): definidas en `DIVISIONES_AUTO_EXPUESTAS` en `config.py`
- **Requieren BOT** (E solo si están en BOT): definidas en `DIVISIONES_REQUIEREN_BOT` en `config.py`

## Caché de IA (DeepSeek)

`ia_carne.py` usa 5 pasos para minimizar llamadas a la API:

1. Tabla `cache_carne` en PostgreSQL (persistente entre sesiones)
2. Lista `PALABRAS_CARNE_OBVIAS` — clasifica como carne sin API
3. Lista `PALABRAS_NO_CARNE_OBVIAS` — clasifica como no-carne sin API
4. Caché en memoria (`_cache_carne_memoria`) — cargada desde DB al inicio
5. Llamada a la API en lotes de 20, resultados guardados en DB inmediatamente

## Personalización

- **Nombres de columnas / divisiones / reglas:** edita `config.py`
- **Agregar/quitar palabras clave:** edita `categorias.json` o usa la interfaz de la app (guarda en DB)
- **Agregar usuarios:** corre `python generar_hash.py` y agrega un bloque en `secrets.toml`
- **Cambiar colores R/E:** edita `COLOR_OK`, `COLOR_ERROR`, `COLOR_BLANK`, `COLOR_INVALID` en `config.py`
- **Modelo DeepSeek / pausa entre lotes:** `DEEPSEEK_MODEL` y `PAUSA_ENTRE_LOTES` en `config.py`
