# Clasificador de Catálogo

Aplicación Streamlit que clasifica artículos de un catálogo de alimentos según reglas de negocio de Sodexo para 12 divisiones. Integra flujos de trabajo basados en Excel y usa IA (DeepSeek API) para detectar productos cárnicos. Los datos persistentes (caché de carne y configuración de palabras clave) se almacenan en PostgreSQL vía Supabase.

## ⚡ Guía rápida (checklist)

Si es la primera vez que tocás este proyecto, seguí estos pasos **en orden**. Cada uno tiene su explicación detallada más abajo — esto es solo el mapa.

**Fase 1 — Preparar cuentas y credenciales (una sola vez):**

- [ ] Crear un proyecto en [Supabase](https://supabase.com) y copiar el connection string → [sección Supabase](#supabase-base-de-datos)
- [ ] Crear una cuenta en [DeepSeek Platform](https://platform.deepseek.com) y generar una API key → [sección Instalación local, paso 3](#instalación-local)
- [ ] Decidir qué usuarios van a poder loguearse en la app (nombre, email, contraseña)

**Fase 2 — Correr la app en tu máquina:**

- [ ] Clonar/copiar el proyecto y crear el entorno virtual
- [ ] `pip install -r requirements.txt`
- [ ] Copiar `secrets.toml.example` → `secrets.toml` y completarlo (cookie, usuarios + hash, API key de DeepSeek, URL de Supabase)
- [ ] `streamlit run app.py` y probar que el login funcione y que se pueda subir un catálogo de prueba

**Fase 3 — Publicar en la nube (Streamlit Community Cloud):**

- [ ] Subir el proyecto a GitHub (sin `secrets.toml`, ese queda afuera por `.gitignore`)
- [ ] Crear la app en [share.streamlit.io](https://share.streamlit.io) apuntando a `app.py`
- [ ] Pegar el contenido completo de tu `secrets.toml` local en **Settings → Secrets** de la app en la nube
- [ ] Deploy y probar de nuevo el login + una subida de catálogo

Con eso la app queda funcionando tanto localmente como en producción, compartiendo la misma base de datos en Supabase.

## Estructura

```
proyecto_catalogo/
├── app.py                         # UI Streamlit: login, carga de 4 archivos, procesamiento, 3 pestañas
├── auth.py                        # Login con streamlit-authenticator (bcrypt)
├── clasificador.py                # Motor de reglas: clasificación + overrides de supplier/división
├── ia_carne.py                    # Cliente DeepSeek con estrategia de 5 pasos y caché
├── utils.py                       # Lectura/escritura Excel, coloreado con openpyxl, detección EXP
├── config.py                      # Configuración maestra: columnas, divisiones, reglas, colores
├── db.py                          # Abstracción PostgreSQL/Supabase: cache_carne, categorias, asignaciones, métricas
├── categorias.json                # Copia local del diccionario de palabras clave (fuente canon: DB)
├── generar_hash.py                # Genera hash bcrypt para secrets.toml
├── importar_cache.py              # Pre-pobla caché de carne desde CSV
├── migrar_a_sql.py                # Genera migracion.sql desde JSON locales (categorias/cache)
├── migrar_asignaciones.py         # Sube data/asignaciones.xlsx a la tabla `asignaciones` en Supabase
├── requirements.txt
├── data/
│   └── asignaciones.xlsx          # Supplier ID → persona encargada (fallback local; la BD es la fuente canon)
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

3. **Conseguir tu API key de DeepSeek:**
   1. Entra a [platform.deepseek.com](https://platform.deepseek.com) y crea una cuenta (o inicia sesión).
   2. Ve a **API keys** en el menú lateral → **Create new API key**.
   3. Ponle un nombre (ej. `catalogo-sodexo`) y copia la key generada (empieza con `sk-...`). **Guárdala ya** — DeepSeek solo la muestra una vez.
   4. Carga saldo si tu cuenta lo requiere (DeepSeek cobra por uso de API, no es gratis ilimitado; revisa precios en su web).

4. **Configurar secrets:**
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```
   Abre `.streamlit/secrets.toml` y completa cada sección. Así se ve un archivo ya completo (valores de ejemplo — **no uses estos, son ficticios**):
   ```toml
   [cookie]
   name = "catalogo_auth"
   key = "9f2a7c1e4b6d8a0f3c5e7b9d1a3f5c7e9b1d3f5a7c9e1b3d5f7a9c1e3b5d7f9a"
   expiry_days = 7

   [credentials.usernames.jperez]
   email = "jperez@sodexo.com"
   name = "Juan Pérez"
   password = "$2b$12$KIXQ1z8yUO9vN3mHf7qLce4tR2xW0pS6bA8dC1eF3gH5jK7lM9nOq"

   [credentials.usernames.mgarcia]
   email = "mgarcia@sodexo.com"
   name = "María García"
   password = "$2b$12$aB3cD5eF7gH9iJ1kL3mN5oP7qR9sT1uV3wX5yZ7aB9cD1eF3gH5iJ"

   [deepseek]
   api_key = "sk-1234567890abcdef1234567890abcdef"

   [connections.db]
   url = "postgresql://postgres.abcdefghijk:MiPasswordReal123@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
   ```
   - `[cookie].key`: cualquier cadena larga y aleatoria sirve (generala con `python -c "import secrets; print(secrets.token_hex(32))"`). Solo se usa para firmar la cookie de sesión, no tiene que ser memorable.
   - `[credentials.usernames.*]`: un bloque por cada persona que pueda loguearse. El nombre después de `usernames.` (ej. `jperez`) es el usuario con el que se loguea, y el `password` **no va en texto plano** — va el hash que genera el siguiente paso.
   - `[deepseek].api_key`: la key que copiaste en el paso 3.
   - `[connections.db].url`: la conexión a Supabase — se explica en el paso 6 / sección [Supabase](#supabase-base-de-datos).

5. **Generar el hash de cada contraseña:**
   ```bash
   python generar_hash.py
   ```
   El script pide la contraseña en texto plano (no la vas a ver en pantalla mientras la escribís, es normal) y devuelve algo así:
   ```
   ============================================================
     Generador de hash de contraseña
   ============================================================
   Ingresa la contraseña: 

   ✅ Hash generado (cópialo a secrets.toml):

   $2b$12$KIXQ1z8yUO9vN3mHf7qLce4tR2xW0pS6bA8dC1eF3gH5jK7lM9nOq

   Ejemplo de uso en secrets.toml:
   [credentials.usernames.juan]
   name = "Juan Pérez"
   email = "juan@empresa.com"
   password = "$2b$12$KIXQ1z8yUO9vN3mHf7qLce4tR2xW0pS6bA8dC1eF3gH5jK7lM9nOq"
   ```
   Copia **solo la línea del hash** (`$2b$12$...`) y pégala como valor de `password` del usuario correspondiente en `secrets.toml`, tal como en el ejemplo del paso 4. Repite el script una vez por cada usuario que necesites crear.

6. **Configurar la base de datos (Supabase):** sigue la sección [Supabase (base de datos)](#supabase-base-de-datos) más abajo y pega la URL de conexión en `secrets.toml` bajo `[connections.db]` (ya está en el ejemplo del paso 4).

7. **Ejecutar la app:**
   ```bash
   streamlit run app.py
   ```
   Deberías ver la pantalla de login. Entra con alguno de los usuarios que configuraste (usuario + la contraseña en texto plano que usaste al generar el hash, **no** el hash).

## Supabase (base de datos)

### 1. Crear el proyecto

1. Entra a [supabase.com](https://supabase.com) → **New project**.
2. Elige organización, nombre del proyecto, contraseña de la base de datos (guárdala, la necesitas para el connection string) y región (idealmente la más cercana al servidor donde corra la app).
3. Espera a que el proyecto termine de aprovisionarse (~2 min).

### 2. Obtener el connection string

1. En el proyecto → **Settings** ⚙️ → **Database** → **Connection string**.
2. Copia la URI en modo **Transaction** (puerto `6543`, recomendado para apps serverless/Streamlit Cloud) o **Session** (puerto `5432`, para uso local prolongado).
3. Reemplaza `[YOUR-PASSWORD]` por la contraseña que definiste al crear el proyecto.
4. Pégala en `.streamlit/secrets.toml` (local) y/o en los Secrets de Streamlit Cloud (ver sección siguiente) bajo:
   ```toml
   [connections.db]
   url = "postgresql://postgres.XXXXXXXX:TU_PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
   ```

### 3. Tablas

No necesitas crear tablas a mano: `db.inicializar_tablas()` se ejecuta automáticamente en el primer arranque de la app (o del primer script que use `db.py`) y crea, si no existen, las siguientes tablas. Es seguro llamarla varias veces (usa `CREATE TABLE IF NOT EXISTS`).

| Tabla | Esquema | Uso |
|-------|---------|-----|
| `cache_carne` | `(producto TEXT PK, es_carne BOOLEAN)` | Caché persistente de clasificación de carne |
| `configuracion` | `(clave TEXT PK, valor TEXT)` | `clave='categorias'` guarda el diccionario serializado |
| `asignaciones` | `(supplier_id TEXT PK, supplier_name, assigned_to, optimized BOOLEAN)` | Supplier ID → persona encargada + flag "Optimized" |
| `metricas_historicas` | `(id, run_id, etiqueta, fecha, dimension, valor, total, matches, errors, blanks, invalid, match_rate)` | Snapshot de métricas de cada corrida, para la pestaña "Metrics History" |

### 4. Migrar datos existentes (opcional)

Si ya tienes datos locales (`data/cache_carne.json`, `categorias.json`, `data/asignaciones.xlsx`) que quieres llevar a un proyecto Supabase nuevo:

1. **Caché de carne + categorías**, genera el SQL y ejecútalo manualmente:
   ```bash
   python migrar_a_sql.py                # genera migracion.sql (cache_carne + categorias + asignaciones sin flag Optimized)
   python migrar_a_sql.py --solo-categorias  # alternativa: solo categorias.json -> migracion_categorias.sql
   ```
   Luego: Supabase → **SQL Editor** → pega el contenido de `migracion.sql` (o `migracion_categorias.sql`) → **Run**.
2. **Asignaciones (Supplier ID → persona + flag Optimized)**, sube directo por Python (no requiere copiar SQL a mano):
   ```bash
   python migrar_asignaciones.py
   ```
   Este script lee `data/asignaciones.xlsx`, se conecta con la URL de `secrets.toml` y reemplaza el contenido completo de la tabla `asignaciones`.
3. **Caché de carne desde un CSV** (por ejemplo un export tipo `Book1.csv`), en vez del JSON:
   ```bash
   python importar_cache.py Book1.csv
   ```

Los tres scripts anteriores requieren que `.streamlit/secrets.toml` ya tenga `[connections.db]` configurado.

## Despliegue en Streamlit Community Cloud

Requiere que Supabase ya esté configurado (sección anterior) y las credenciales de `secrets.toml` listas.

### 1. Subir el proyecto a GitHub

El repo local todavía no es un repositorio git, así que primero hay que inicializarlo y publicarlo (Streamlit Cloud despliega directamente desde un repo de GitHub):

```bash
git init
git add .
git commit -m "Initial commit"
```

`.streamlit/secrets.toml` está en `.gitignore`, así que **no se sube** — solo se sube `secrets.toml.example` como plantilla. Verifica con `git status` que ningún secreto quedó incluido antes del push.

Crea un repositorio vacío en GitHub (por ejemplo `sodexo/proyecto-catalogo`) y conéctalo:

```bash
git remote add origin https://github.com/TU_USUARIO/proyecto_catalogo.git
git branch -M main
git push -u origin main
```

### 2. Crear la app en Streamlit Cloud

1. Entra a [share.streamlit.io](https://share.streamlit.io) con tu cuenta (puedes iniciar sesión con GitHub).
2. Clic en **Create app** → **Deploy a public app from GitHub** (o "from an existing repo").
3. Selecciona el repositorio, la rama (`main`) y el archivo principal: `app.py`.
4. Elige el nombre de la URL de la app (ej. `sodexo-catalog-classifier`).

### 3. Configurar los Secrets

Antes de darle a Deploy (o justo después, desde **Settings → Secrets** en el menú ⋮ de la app):

1. Abre el editor de Secrets en la app.
2. Pega **todo el contenido** de tu `.streamlit/secrets.toml` local (cookie, credentials, deepseek, connections.db) — el editor de Streamlit Cloud usa el mismo formato TOML.
3. Guarda. La app se reinicia automáticamente y toma los nuevos secrets.

### 4. Deploy

1. Clic en **Deploy**. Streamlit Cloud instala `requirements.txt` y arranca `app.py`.
2. La primera vez, `db.inicializar_tablas()` crea las tablas en Supabase si aún no existen (ver sección Supabase arriba) — no hace falta correr migraciones manuales si partes de un proyecto Supabase vacío.
3. Si vienes migrando datos existentes, corre `migrar_a_sql.py` / `migrar_asignaciones.py` / `importar_cache.py` **antes** o **después** del deploy indistintamente (apuntan directo a Supabase, no a la app).

### 5. Actualizaciones posteriores

- **Cambios de código:** cada `git push` a la rama configurada dispara un redeploy automático.
- **Cambios en `config.py` / `categorias.json` / reglas:** requieren push + redeploy (o "Reboot app" desde el menú ⋮) para tomar efecto.
- **Cambios de secrets** (nuevas API keys, usuarios, URL de DB): edítalos desde **Settings → Secrets**; la app se reinicia sola.
- **`data/asignaciones.xlsx`:** el filesystem de Streamlit Cloud es efímero (se resetea en cada redeploy), así que en producción la fuente de verdad es la tabla `asignaciones` en Supabase, no el archivo local. Actualiza asignaciones corriendo `migrar_asignaciones.py` localmente (apunta a la misma URL de Supabase) en vez de editar el Excel dentro del servidor.

## Flujo de datos

El usuario sube 4 archivos Excel → validación de columnas → reglas de clasificación → consulta IA para ítems "Local" → reporte Excel coloreado con discrepancias EXP marcadas en rojo → descarga.

| Archivo | Descripción |
|---------|-------------|
| Catalog | Catálogo principal de productos |
| BOT | Archivo de órdenes (determina exposición en divisiones BOT) |
| EXP | Archivo de exposición; discrepancias se marcan en rojo |
| BOT Charcuterie | Ítems non-contracted expuestos en divisiones excepto SCHOOL SERVICES |

## Reglas de clasificación (orden de prioridad)

0. **Descripción inválida** (número puro, texto muy corto, solo símbolos) → marcado `⚠️ Revisar`, todas las divisiones en `INVALID`
0.5. **Non-contracted por keyword + proveedor** (`REGLAS_NON_CONTRACTED_POR_SUPPLIER`, modo "fuertes") → R en todas, sin que el BOT Charcuterie pueda exponerlo. Gana sobre Local, Dairy/GnG, Bakery, PPI e Initial Catalog (ej.: "CFA", 5 proveedores). Las reglas marcadas con `categorias_restringidas` se evalúan al final y solo convierten items cuya categoría base esté en esa lista, respetando Banned/Local/Dairy/Bakery (ej.: "Panera", restringida a Initial Catalog + PPI). Las listas de IDs están en `config.py`.
1. **Banned** → R en todas las divisiones
2. **Local + es carne** (consulta DeepSeek) → R en todas
2.1. **Local + no es carne** → E en todas
2.5. **Flores** (`PALABRAS_FLOR`, salvo `PALABRAS_FLOR_EXCLUIDAS`) → sin "edible": Non-contracted (R en todas); con "edible": Initial Catalog (School Services se fuerza a R vía overrides)
3. **Dairy / Grab and Go / Bakery** (depende del proveedor, `SUPPLIERS_DAIRY_GNG`) → si el proveedor tiene el permiso en `True`, E en todas las divisiones (categoría Dairy, Grab and Go, Dairy/GnG o Bakery); si no lo tiene o el proveedor no está en la lista, Non-contracted (R en todas)
4. **Non-contracted** (frozen, organic, proteínas, formatos, etc.) → R en todas
5. **PPI** (cortado, rebanado, rallado, etc.) → E en todas
6. **Initial Catalog** (por descarte, sin whitelist) → E automático en `DIVISIONES_AUTO_EXPUESTAS`; en `DIVISIONES_REQUIEREN_BOT` depende del archivo BOT — salvo que el proveedor asignado tenga `Optimized = FALSE`, en cuyo caso se expone (E) en todas sin consultar el BOT

Después de clasificar se aplican cuatro capas de overrides (en orden):
- `REGLAS_ESPECIFICAS_POR_DIVISION` — overrides R/E por palabra clave y división (búsqueda estricta, sin palabras pegadas)
- `REGLAS_ESPECIFICAS_POR_SUPPLIER` — overrides R/E por proveedor
- `EXCEPCIONES_POR_SKU_SUPPLIER` / `EXCEPCIONES_POR_CATEGORIA_SUPPLIER` — excepciones que fuerzan E para SKUs o categorías específicas de un proveedor en divisiones específicas
- `EXCEPCIONES_POR_KEYWORDS_SUPPLIER` — fuerza E para un proveedor cuando la descripción contiene ciertas palabras clave (AND/OR configurable), con palabras de exclusión opcionales

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

## Interfaz (3 pestañas)

- **📊 Main Dashboard** — métricas generales, resumen por persona (`data/asignaciones.xlsx` o tabla `asignaciones`), filtros, tabla de resultados y descarga del Excel coloreado
- **🔍 Detailed Analysis** — drill-down por persona / división / categoría
- **📈 Metrics History** — evolución del % Match a través de corridas, usando la tabla `metricas_historicas` (se guarda automáticamente en cada procesamiento)

## Personalización

- **Nombres de columnas / divisiones / reglas:** edita `config.py`
- **Agregar/quitar palabras clave (Banned, Non-contracted, PPI):** edita `categorias.json` o usa la interfaz de la app (guarda en DB)
- **Permisos de Dairy / Grab and Go / Bakery por proveedor:** `SUPPLIERS_DAIRY_GNG` en `config.py`; palabras clave en `PALABRAS_DAIRY`, `PALABRAS_GRAB_AND_GO`, `PALABRAS_BAKERY`
- **Lógica de flores / bean sprouts:** `PALABRAS_FLOR`, `PALABRAS_FLOR_EXCLUIDAS`, `PALABRAS_BEAN_SPROUTS` en `config.py`
- **Excepciones y overrides por proveedor:** `REGLAS_NON_CONTRACTED_POR_SUPPLIER`, `REGLAS_ESPECIFICAS_POR_SUPPLIER`, `EXCEPCIONES_POR_SKU_SUPPLIER`, `EXCEPCIONES_POR_CATEGORIA_SUPPLIER`, `EXCEPCIONES_POR_KEYWORDS_SUPPLIER` en `config.py`
- **Agregar usuarios:** corre `python generar_hash.py` y agrega un bloque en `secrets.toml`
- **Cambiar colores R/E:** edita `COLOR_OK`, `COLOR_ERROR`, `COLOR_BLANK`, `COLOR_INVALID`, `COLOR_BOT_MISMATCH` en `config.py`
- **Modelo DeepSeek / pausa entre lotes:** `DEEPSEEK_MODEL` y `PAUSA_ENTRE_LOTES` en `config.py`
- **Asignaciones (Supplier ID → persona, flag Optimized):** edita `data/asignaciones.xlsx` y corre `python migrar_asignaciones.py` para subirlo a la tabla `asignaciones`

### ¿Qué es el flag "Optimized"?

Cada proveedor en `data/asignaciones.xlsx` (columna `Optimized`, ver `COL_ASSIGN_OPTIMIZED` en `config.py`) tiene un flag `TRUE`/`FALSE` que solo afecta a los productos que llegan a la regla 6 (**Initial Catalog por descarte**, es decir, productos que no cayeron en ninguna regla anterior — no son Banned, ni Local, ni Non-contracted, ni PPI, ni flor, ni Dairy/GnG):

- **`TRUE`** (proveedor "optimizado"): para las divisiones en `DIVISIONES_REQUIEREN_BOT`, la exposición depende de si el producto aparece en el archivo BOT que subió el usuario. Es el comportamiento normal/estricto.
- **`FALSE`** (proveedor "no optimizado"): el producto se expone (`E`) directamente en **todas** las divisiones, sin mirar el archivo BOT. Se usa para proveedores donde ya se sabe que todo lo que llega a esa regla debe exponerse igual, y pedirle al usuario que lo confirme vía BOT sería trabajo repetido.

Si un Supplier ID no aparece en `asignaciones` (ni en el Excel ni en la tabla), se asume `Optimized = TRUE` (comportamiento estricto por defecto). Para cambiarlo: editá el Excel, corré `python migrar_asignaciones.py`, y el cambio queda en Supabase (afecta tanto a la app local como a la de producción, porque ambas leen la misma base).

## Troubleshooting (errores comunes)

**"Could not connect to database" / errores de conexión a Supabase**
- Revisá que `[connections.db].url` en `secrets.toml` no tenga `[YOUR-PASSWORD]` sin reemplazar — es el error más común.
- Confirmá que copiaste la URL completa, sin cortar caracteres al final.
- Si estás en Streamlit Cloud, probá el modo **Transaction** (puerto `6543`) en vez de **Session** (`5432`) — el pooler de sesión a veces no acepta conexiones desde entornos serverless.
- Verificá en Supabase → **Settings → Database** que el proyecto no esté pausado (los proyectos free se pausan tras varios días sin uso; hay un botón para reactivarlo).

**"Invalid API key" / errores al llamar a DeepSeek**
- Confirmá que copiaste la key completa (empieza con `sk-`) sin espacios extra al copiar/pegar.
- Verificá que la cuenta de DeepSeek tenga saldo/crédito disponible — una key válida igual falla si no hay saldo.
- El campo en `secrets.toml` debe ser `[deepseek]` con `api_key = "..."` (no `[groq]`, salvo que hayas migrado el código para usar Groq en vez de DeepSeek).

**La app pide login pero ningún usuario/contraseña funciona**
- Asegurate de loguearte con la contraseña **en texto plano** (la que escribiste en `generar_hash.py`), no con el hash `$2b$12$...`.
- Revisá que el hash en `secrets.toml` esté completo y entre comillas dobles, sin saltos de línea en el medio (TOML es sensible a esto si copiás mal).
- Si cambiaste `secrets.toml` mientras la app corría localmente, reiniciá `streamlit run app.py` — no siempre recarga los secrets en caliente.

**Error de permisos / "You don't have access" al crear la app en Streamlit Cloud**
- Confirmá que tu cuenta de Streamlit Cloud está conectada al mismo usuario/organización de GitHub donde está el repo.
- Si el repo es privado, autorizá a Streamlit Cloud a acceder a repos privados desde **Settings → GitHub** en tu cuenta de Streamlit Cloud (te lo suele pedir automáticamente al elegir el repo).
- Si el repo pertenece a una organización de GitHub, puede que necesites que un admin de la organización apruebe el acceso de la app "Streamlit" en GitHub → **Settings → Applications**.

**La app en producción no refleja cambios en `data/asignaciones.xlsx`**
- Esperado: el filesystem de Streamlit Cloud es efímero. Corré `python migrar_asignaciones.py` localmente (apuntando a la misma URL de Supabase) — eso sí persiste, porque escribe en la base de datos, no en un archivo del servidor.

**Cambié `categorias.json` pero la app sigue usando las categorías viejas**
- La fuente de verdad es la tabla `configuracion` en Supabase, no el archivo local. Editar `categorias.json` a mano no alcanza — usá la interfaz de la app para modificar categorías (guarda directo en DB), o corré `migrar_a_sql.py --solo-categorias` y ejecutá el SQL resultante en Supabase.

**`ModuleNotFoundError` al correr cualquier script (`migrar_a_sql.py`, `importar_cache.py`, etc.)**
- Confirmá que activaste el entorno virtual (`venv\Scripts\activate` en Windows) antes de correr el script, y que corriste `pip install -r requirements.txt` dentro de ese entorno.
