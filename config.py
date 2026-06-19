"""
================================================================================
ARCHIVO DE CONFIGURACIÓN
================================================================================
⚠️ AQUÍ ES DONDE DEBES MODIFICAR LOS NOMBRES DE COLUMNAS si tu Excel los tiene
   con otro nombre, en otro idioma, o cambian en el futuro.

Solo cambia el valor a la derecha del "=" (entre comillas).
================================================================================
"""

# ------------------------------------------------------------------------------
# FILAS A SALTAR AL LEER LOS EXCEL
# ------------------------------------------------------------------------------
# Si tu Excel tiene filas de encabezado/título antes de la fila con los nombres
# de columna, indica cuántas filas saltar.


SKIP_ROWS_CATALOGO = 3   # Catálogo: salta las 3 primeras filas
SKIP_ROWS_BOT      = 0   # BOT: por defecto no salta ninguna

# ------------------------------------------------------------------------------
# COLUMNAS DEL ARCHIVO CATÁLOGO
# ------------------------------------------------------------------------------
COL_SKU            = "Supplier SKU"       # Número de producto
COL_ITEM           = "Item Description"   # Nombre del producto
COL_SUPPLIER       = "Supplier Name"      # Distribuidor/proveedor
COL_SUPPLIER_ID    = "Supplier ID"        # ID del proveedor

# ------------------------------------------------------------------------------
# DIVISIONES (las 12 columnas R/E que existen en el Excel)
# ------------------------------------------------------------------------------
# IMPORTANTE: cada división debe estar EN SOLO UNA de las dos listas de abajo
# (auto-expuestas O requieren-bot), nunca en las dos.

DIVISIONES = [
    "UNIVERSITIES",
    "HOSPITALS",
    "SENIOR LIVING",
    "AIRLINE LOUNGES",
    "SPORTS & LEISURE",
    "SCHOOL SERVICES",
    "LEISURE DIVISION",
    "CORPORATE SERVICES",
    "GOVERNMENT SERVICES",
    "SPECIAL PROJECTS",
    "ENERGY US",
    "CONVENIENCE SOLUTIONS",
]

# Algunos archivos de catálogo traen las columnas con nombres alternativos.
# Este mapa traduce esos alias al nombre canónico usado en DIVISIONES.
# La búsqueda es case-insensitive y se ignoran espacios extra.
# Si el archivo trae una columna con cualquiera de las CLAVES, se renombra
# automáticamente al VALOR antes de procesar.
ALIASES_COLUMNAS = {
    "CENTERPLATE": "SPORTS & LEISURE",
    "Centerplate": "SPORTS & LEISURE",
    "CORPORATE SERVICES SEGMENT (US)": "CORPORATE SERVICES",
    "CORPORATE SERVICES SEGMENT US": "CORPORATE SERVICES",
    "AIRLINES": "AIRLINE LOUNGES",
    # Agrega más alias aquí si encuentras otras variantes en archivos futuros:
    # "NOMBRE ALTERNATIVO": "NOMBRE CANONICO",
}

# Si el producto cae en "Initial Catalog", estas divisiones se EXPONEN
# automáticamente, SIN consultar el archivo BOT.
DIVISIONES_AUTO_EXPUESTAS = [
    "AIRLINE LOUNGES",
    "SPORTS & LEISURE",
    "SCHOOL SERVICES",
    "LEISURE DIVISION",
    "GOVERNMENT SERVICES",
    "SPECIAL PROJECTS",
    "ENERGY US", 
    "CONVENIENCE SOLUTIONS",
]

# Si el producto cae en "Initial Catalog", estas divisiones consultan el BOT:
#   - SI el SKU está en BOT  → "E"
#   - NO está en BOT          → "R"
DIVISIONES_REQUIEREN_BOT = [
    "UNIVERSITIES",
    "HOSPITALS",
    "SENIOR LIVING",
    "CORPORATE SERVICES",
]

# ------------------------------------------------------------------------------
# Validación automática (no tocar): se ejecuta al importar el archivo y avisa
# si una división quedó duplicada o faltante.
# ------------------------------------------------------------------------------
_set_auto = set(DIVISIONES_AUTO_EXPUESTAS)
_set_bot  = set(DIVISIONES_REQUIEREN_BOT)
_set_all  = set(DIVISIONES)

_duplicadas = _set_auto & _set_bot
if _duplicadas:
    raise ValueError(
        f"⚠️ Estas divisiones están en AMBAS listas (corrige config.py): {_duplicadas}"
    )
_faltantes = _set_all - (_set_auto | _set_bot)
if _faltantes:
    raise ValueError(
        f"⚠️ Estas divisiones de DIVISIONES no están en ninguna lista: {_faltantes}"
    )
_extras = (_set_auto | _set_bot) - _set_all
if _extras:
    raise ValueError(
        f"⚠️ Estas divisiones no existen en DIVISIONES pero sí en sub-listas: {_extras}"
    )


# Validar que las divisiones de REGLAS_ESPECIFICAS_POR_DIVISION existan
def _validar_reglas_especificas():
    """Verifica que cada regla específica use divisiones válidas."""
    for i, regla in enumerate(globals().get("REGLAS_ESPECIFICAS_POR_DIVISION", [])):
        for clave in ("divisiones_restringidas", "divisiones_expuestas"):
            divs = regla.get(clave, [])
            invalidas = set(divs) - _set_all
            if invalidas:
                raise ValueError(
                    f"⚠️ Regla #{i+1} ('{regla.get('nombre','?')}') usa divisiones "
                    f"que no existen en DIVISIONES: {invalidas}"
                )

# ------------------------------------------------------------------------------
# REGLA DAIRY / GRAB AND GO POR SUPPLIER
# ------------------------------------------------------------------------------
# Algunos suppliers tienen permitido vender Dairy o Grab and Go.
# Si el producto contiene palabras de Dairy o Grab and Go Y el supplier está
# en esta lista con "yes", se EXPONE en todas las divisiones.
# Si está con "no", se RESTRINGE (Non-contracted).
# Si el supplier NO está en esta lista pero el item matchea estas palabras,
# se trata como Non-contracted (R en todas).
SUPPLIERS_DAIRY_GNG = {
    "1105082": {"dairy": True, "grab_and_go": True},   # Charlie's Anchorage - Sodexo
    "1104041": {"dairy": True, "grab_and_go": True},   # Charlie's Portland - Sodexo
    "1111823": {"dairy": True, "grab_and_go": True},   # Charlie's Salt Lake City - Sodexo
    "1000290": {"dairy": True, "grab_and_go": True},   # Charlie's Seattle - Sodexo
    "1000291": {"dairy": True, "grab_and_go": True},   # Charlie's Spokane - Sodexo
    "1118971": {"dairy": True, "grab_and_go": False},  # Daylight Foods Inc. - Sodexo
    "1000240": {"dairy": True, "grab_and_go": False},  # J. Ambrogi Foods - Sodexo
    "1000233": {"dairy": True, "grab_and_go": True},   # Kegel's Produce - Sodexo
    "1000231": {"dairy": True, "grab_and_go": True},   # La Grasso Bros. Produce - Sodexo
    "1108121": {"dairy": True, "grab_and_go": True},   # Liberty Fruit - Sodexo
    "1000647": {"dairy": True, "grab_and_go": True},   # Limehouse Produce - Sodexo
    "1000253": {"dairy": True, "grab_and_go": True},   # M. Saunders Wholesale
    "1000251": {"dairy": True, "grab_and_go": False},  # Mento Produce - Sodexo
    "1000484": {"dairy": True, "grab_and_go": False},  # T. Castro Produce Inc.
    "1123636": {"dairy": True, "grab_and_go": False},  # Vesta Foodservice - AZ - Sodexo
    "1122261": {"dairy": True, "grab_and_go": False},  # Vesta Foodservice - LA - Sodexo
    "1118967": {"dairy": True, "grab_and_go": False},  # Vesta Foodservice - San Fran - Sodexo
    "1000261": {"dairy": True, "grab_and_go": True},   # BIX PRODUCE CO INC - FRESHPOINT
    "1000305": {"dairy": True, "grab_and_go": True},   # FRESHPOINT CENTRAL CALIFORNIA INC
    "1000308": {"dairy": True, "grab_and_go": True},   # FRESHPOINT CENTRAL FLORIDA
    "1000304": {"dairy": True, "grab_and_go": True},   # FRESHPOINT CHARLOTTE
    "1000300": {"dairy": True, "grab_and_go": True},   # FRESHPOINT CONNECTICUT
    "1000316": {"dairy": True, "grab_and_go": True},   # FRESHPOINT DALLAS
    "1000269": {"dairy": True, "grab_and_go": True},   # FRESHPOINT HAWAII LLC DBA ARMSTRONG PRODUCE LTD
    "1000302": {"dairy": True, "grab_and_go": True},   # FRESHPOINT NASHVILLE
    "1000315": {"dairy": True, "grab_and_go": True},   # FRESHPOINT OF ATLANTA
    "1000312": {"dairy": True, "grab_and_go": True},   # FRESHPOINT OF DENVER
    "1000296": {"dairy": True, "grab_and_go": True},   # FRESHPOINT OKLAHOMA CITY
    "1000303": {"dairy": True, "grab_and_go": True},   # FRESHPOINT RALEIGH
    "1000299": {"dairy": True, "grab_and_go": True},   # FRESHPOINT SOUTH FLORIDA INC
    "1000295": {"dairy": True, "grab_and_go": True},   # FRESHPOINT SOUTH TEXAS LP SAN ANTONIO
    "1000313": {"dairy": True, "grab_and_go": True},   # FRESHPOINT SOUTHERN CALIFORNIA INC
    "1000311": {"dairy": True, "grab_and_go": True},   # FRESHPOINT SAN FRANCISCO INC UPS A66V42
    "1000246": {"dairy": True, "grab_and_go": True},   # PARAGON MONTEVERDE FOOD SERVICE- FRESHPOINT
    "1129301": {"dairy": True, "grab_and_go": False},  # OLE TYME PRODUCE
    "1137793": {"dairy": True, "grab_and_go": False},  #charlies produce boise
    "1118198": {"dairy": True, "grab_and_go": False},  #FRESH EDGE - CITY PRODUCE OF FORT WALTON BEACH
    "1000944": {"dairy": True, "grab_and_go": False},  #MIDWEST INSTITUTIONAL
    "1001244": {"dairy": True, "grab_and_go": True},  #MIDWEST INSTITUTIONAL
}

PALABRAS_DAIRY = [
    "milk", "half & half", "half and half", "half half", "heavy cream","milk gallon","milk whole gallon",
    "milk organic","organic milk", "milkorganic", "organicmilk", "milk oat org","milk org","org milk",
    "milk soy org", "milk soy organic", "cottage cheese", "sour cream", "yogurt"
]

PALABRAS_GRAB_AND_GO = [
    "snack", "gng", "go", "wrap", "sandwich", "sand", "sand*", "sndw", "grab & go", "grab n go", 
    "grab-and-go","grab 'n go","meal","parfait"," panini ham", "mkw",
    "cesar salad", "caesar salad", "chicken salad", "burrito", "wrap", "saladcaesar",
    "saladcharlies","salad charlies", "snack pack", "snackpack", "snack-pack",
    "hk", "side", "CF CASE ENTRÉE", "CF CASE MAP", "CF CASE SALAD", "CF CASE SANDW", 
    "CF SUB", "CHI MEIBAO BUN", "CAESAR SALAD","burrito breakfast", "saladcpf","saladgarden",
    "GARDEN SALAD", "Grab N Go", "Gummy", "Hk Salad", "Hk Burrito", "Hk Entrée","saladgreek",
    "Hk breakfast burrito", "fresh salad red bliss potatoe", "cobb salad", "greek salad", 
    "southwest chkn salad", "cf map salad", "fresh salad","salad","meal","breakfast",
    "carrot/Broccoli Cup","Carrot/celery Cup", "snak pak"
]

# ------------------------------------------------------------------------------
# LÓGICA DE FLORES (clasificación en clasificar_categoria)
# ------------------------------------------------------------------------------
# Si el item contiene alguna de estas palabras, NO entra al flujo de flores
# (se clasifica normalmente con las demás reglas).
PALABRAS_FLOR_EXCLUIDAS = [
    "cauliflower", "flowering", "broccoflower", "sprouts",
    "cauliflowercello", "cauliflowerbaby",
]

# Si el item contiene alguna de estas palabras (y no está excluido arriba):
#   - SIN "edible" → Non-Contracted (R todas las divisiones)
#   - CON "edible" → Initial Catalog; School Services forzado a R via
#                    REGLAS_ESPECIFICAS_POR_DIVISION, el resto pasa por BOT
PALABRAS_FLOR = ["flow", "flower*"]

# ------------------------------------------------------------------------------
# REGLAS ESPECÍFICAS POR DIVISIÓN (override del cálculo normal)
# ------------------------------------------------------------------------------
# Estas reglas se aplican DESPUÉS del cálculo normal de R/E.
# Si un item contiene cualquiera de las "palabras_clave" (con plural automático
# y búsqueda case-insensitive), las divisiones listadas en
# "divisiones_restringidas" se forzarán a "R", y las listadas en
# "divisiones_expuestas" se forzarán a "E".
#
# La categoría del producto NO cambia — sigue siendo lo que era (Non-contracted,
# Initial Catalog, etc.). Solo se sobrescriben las celdas R/E afectadas.
#
# Para agregar una nueva regla, simplemente añade un nuevo diccionario a la
# lista. Puedes mezclar palabras y divisiones con total libertad.
REGLAS_ESPECIFICAS_POR_DIVISION = [
    {
        # "edible" + ("flow" o "flower") → School Services siempre R.
        # Las demás divisiones siguen el flujo normal de Initial Catalog (BOT).
        "nombre": "Edible flowers: School Services siempre R",
        "palabras_clave": ["flow", "flower*"],  # al menos una (OR)
        "palabras_todas": ["edible"],           # todas deben estar presentes (AND)
        "divisiones_restringidas": ["SCHOOL SERVICES"],
        "divisiones_expuestas": [],
    },
    # Plantilla para agregar más reglas en el futuro:
    # {
    #     "nombre": "Descripción corta de la regla",
    #     "palabras_clave": ["palabra1", "palabra2"],   # OR: al menos una
    #     "palabras_todas": ["requerida1"],              # AND: todas deben estar
    #     "divisiones_restringidas": ["DIVISION_A"],
    #     "divisiones_expuestas": [],
    # },
]

# ------------------------------------------------------------------------------
# REGLAS ESPECÍFICAS POR SUPPLIER
# ------------------------------------------------------------------------------
# Para algunos suppliers, todas sus divisiones deben ir RESTRINGIDAS (R) por
# defecto, EXCEPTO en las divisiones listadas en "divisiones_normales", donde
# se aplican las reglas estándar (banned, local, non-contracted, etc.).
#
# Ejemplo: Daylight foods (supplier_id 1118971) solo puede vender a SCHOOL
# SERVICES con criterios normales; en todas las demás divisiones, sus
# productos van a "R" automáticamente.
#
# Si el supplier_id está en esta lista, esta regla se aplica DESPUÉS de la
# clasificación normal y SOBREESCRIBE el valor R/E de las divisiones que NO
# están en "divisiones_normales".
REGLAS_ESPECIFICAS_POR_SUPPLIER = [
    {
        "nombre": "Daylight foods: solo School Services expuesto, sin BOT",
        "supplier_ids": ["1118971"],
        "divisiones_normales": ["SCHOOL SERVICES"],
        # True = no pasa por BOT; School Services siempre E, las demás siempre R
        "forzar_expuesto_en_normales": True,
    },
    # Plantilla para agregar más reglas por supplier en el futuro:
    # {
    #     "nombre": "Descripción corta",
    #     "supplier_ids": ["12345", "67890"],
    #     "divisiones_normales": ["DIVISION_X"],
    # },
]

# ------------------------------------------------------------------------------
# EXCEPCIONES ESPECÍFICAS POR SKU + SUPPLIER
# ------------------------------------------------------------------------------
# Permite forzar "E" en divisiones concretas para SKUs individuales de un
# supplier, independientemente de la clasificación estándar.
# Se aplica DESPUÉS de todas las demás reglas (incluidas REGLAS_POR_SUPPLIER).
# divisiones_expuestas: lista de divisiones canónicas, o None para todas.
EXCEPCIONES_POR_SKU_SUPPLIER = [
    {
        "nombre": "Black River - Beef Ground: expuesto en UNIV/CORP/HOSP/SENIOR",
        "supplier_id": "1000259",
        "skus": ["191430", "192951", "174353", "174663"],
        "divisiones_expuestas": ["UNIVERSITIES", "CORPORATE SERVICES", "HOSPITALS", "SENIOR LIVING"],
    },
    {
        "nombre": "Black River - Non-contracted: expuesto en todas las divisiones",
        "supplier_id": "1000259",
        "skus": [
            "187277", "20162592", "172307", "172356", "172391", "20164015",
            "20164012", "20164009", "178154", "20164372", "20164368", "20164374",
            "20164367", "20164371", "20164369", "20164376", "20164373", "20164370",
            "20164375",
        ],
        "divisiones_expuestas": None,  # None = todas las divisiones
    },
]

# ------------------------------------------------------------------------------
# EXCEPCIONES ESPECÍFICAS POR KEYWORDS + SUPPLIER
# ------------------------------------------------------------------------------
# Fuerza "E" en divisiones concretas para items de un supplier cuya descripción
# contenga todas las palabras en "palabras_todas" y ninguna en "palabras_excluidas".
# Se aplica DESPUÉS de EXCEPCIONES_POR_CATEGORIA_SUPPLIER.
EXCEPCIONES_POR_KEYWORDS_SUPPLIER = []


# ------------------------------------------------------------------------------
# EXCEPCIONES ESPECÍFICAS POR CATEGORÍA + SUPPLIER
# ------------------------------------------------------------------------------
# Fuerza "E" en divisiones concretas para todos los items de un supplier que
# caigan en una categoría determinada. Independiente de EXCEPCIONES_POR_SKU_SUPPLIER.
# divisiones_expuestas: lista de divisiones canónicas, o None para todas.
EXCEPCIONES_POR_CATEGORIA_SUPPLIER = [
    {
        "nombre": "Black River - Local Meat expuesto en todas menos SCHOOL SERVICES",
        "supplier_id": "1000259",
        "categorias": ["Local Meat"],
        "divisiones_expuestas": [d for d in DIVISIONES if d != "SCHOOL SERVICES"],
    },
    {
        "nombre": "Native Maine - Local Meat expuesto en todas menos SCHOOL SERVICES",
        "supplier_id": "1000641",
        "categorias": ["Local Meat"],
        "divisiones_expuestas": [d for d in DIVISIONES if d != "SCHOOL SERVICES"],
    },
]

# ------------------------------------------------------------------------------
# COLUMNAS DEL ARCHIVO BOT
# ------------------------------------------------------------------------------
COL_BOT_SKU      = "SI_SKU"   # Columna en BOT que contiene el número de producto
COL_BOT_SUPPLIER = "PCC_NM"   # Columna en BOT que contiene el nombre del proveedor

# ------------------------------------------------------------------------------
# COLUMNAS DEL ARCHIVO BOT CHARCUTERIE
# ------------------------------------------------------------------------------
COL_BOT_CHAR_SUPPLIER = "PCC_NBR"   # Columna del proveedor
COL_BOT_CHAR_SKU      = "SI_SKU"    # Columna del número de ítem (se usa para matching)
COL_BOT_CHAR_DESCR    = "SI_DESCR"  # Columna de descripción
SKIP_ROWS_BOT_CHAR    = 0

# Divisiones donde aplica el BOT Charcuterie (todas excepto SCHOOL SERVICES)
DIVISIONES_BOT_CHARCUTERIE = [d for d in DIVISIONES if d != "SCHOOL SERVICES"]

# ------------------------------------------------------------------------------
# COLUMNAS DEL ARCHIVO EXP
# ------------------------------------------------------------------------------
COL_EXP_SKU         = "Supplier SKU"
COL_EXP_SUPPLIER_ID = "Supplier ID"
COL_EXP_DIVISION    = "Division"
SKIP_ROWS_EXP       = 0

# ------------------------------------------------------------------------------
# COLUMNAS DEL ARCHIVO DISTRIBUIDORES (assigned)
# ------------------------------------------------------------------------------
# El match con el catálogo se hace por SUPPLIER ID (más confiable que el nombre).
# El nombre del distribuidor sigue mostrándose en la tabla final.
COL_ASSIGN_SUPPLIER_ID = "Supplier ID"     # ID del distribuidor (para hacer match)
COL_ASSIGN_SUPPLIER    = "Supplier Name"   # Nombre del distribuidor (para mostrar)
COL_ASSIGN_PERSON      = "Assigned to"     # Persona encargada
COL_ASSIGN_OPTIMIZED   = "Optimized"       # TRUE = pasa por proceso BOT; FALSE/vacío = E en todas las divisiones
RUTA_ASIGNACIONES      = "data/asignaciones.xlsx"

# ------------------------------------------------------------------------------
# CONFIGURACIÓN DE GEMINI
# ------------------------------------------------------------------------------
#GROQ_MODEL = "llama-3.3-70b-versatile"
DEEPSEEK_MODEL = "deepseek-v4-flash"  # rápido y barato, ideal para clasificación
# (el modelo anterior "deepseek-chat" se deprecia el 24-jul-2026)

PAUSA_ENTRE_LOTES = 0.3  # DeepSeek es más permisivo que Groq, puedes bajarla
# Lista local de palabras que SIEMPRE se consideran carne (sin llamar a la IA).
# Útil para ahorrar cuota y para items obvios. Cuando un producto Local contiene
# alguna de estas palabras, NO se consulta a Gemini, se marca directamente como
# carne. Solo se consulta a Gemini si NO contiene ninguna palabra obvia.
PALABRAS_CARNE_OBVIAS = [
    "beef", "pork", "chicken", "chx", "chix", "turkey", "lamb", "veal",
    "duck", "bison", "boar", "venison", "rabbit", "quail",
    "fish", "salmon", "tuna", "trout", "tilapia", "snapper", "shrimp",
    "lobster", "crab", "oyster", "mussels", "clam", "scallop", "squid",
    "sardines", "anchovies", "prawn", "caviar",
    "ham", "bacon", "sausage", "salami", "salame", "soppressata",
    "prosciutto", "mortadella", "chorizo", "pepperoni",
    "meatball", "burger", "patty", "nugget", "tenderloin",
    "steak", "stk", "ribeye", "sirloin", "brisket", "filet", "fillet",
    "rib", "loin", "ground beef", "ground turkey", "ground chicken",
    "wagyu", "angus", "wing", "drumstick", "thigh", "breast",
]

# Lista de palabras que NUNCA son carne (lácteos, vegetales obvios).
# Si el producto contiene alguna, NO se consulta a groq.
PALABRAS_NO_CARNE_OBVIAS = [
    "milk", "yogurt", "yoghurt", "cheese", "cream", "butter",
    "juice", "water", "tea", "coffee", "lemonade", "soda",
    "apple", "banana", "orange", "lemon", "lime", "grape",
    "lettuce", "spinach", "carrot", "onion", "garlic", "potato",
    "bread", "flour", "rice", "pasta", "noodle",
    "sugar", "salt", "honey", "oil", "egg", "eggs", "lentil", "mushroom", "mushrooms", "tomato", "tomatoes",
    "salad", "appetizer", "appt", "artichoke", "sand", "sandwich",
]

# ------------------------------------------------------------------------------
# EXCEPCIONES: items que NO son carne aunque contengan palabras de carne
# ------------------------------------------------------------------------------
EXCEPCIONES_NO_CARNE = [
    # Empaques y contenedores
    "clamshell", "clamshells",

    # Hongos con nombres de carne/marisco
    "lobster mushroom", "mushroom lobster", "mushrooms lobster",
    "oyster mushroom", "oyster mushrooms",
    "mushroom oyster", "mushrooms oyster", "mushroomoyster",
    "blue oyster", "king oyster",
    "chicken of the woods", "chicken mushroom",
    "beefsteak mushroom", "mushroom beefsteak",
    "hen of the woods", "hen mushroom",

    # Vegetales/frutas con nombres de carne
    "beefsteak tomato", "beefsteak tomatoes",
    "tomato beefsteak", "tomatoes beefsteak",
    "lentil caviar", "vegetable caviar", "lentils caviar",
    "black caviar", "lentil black caviar",
    "caviar lentil", "caviar lentils",

    # Especias y condimentos con nombre confuso
    "chicken rub", "chicken seasoning", "chicken spice",
    "beef rub", "beef seasoning",
    "fish sauce", "anchovy paste",
]
# ------------------------------------------------------------------------------
# COLORES PARA EL MODELO DE CONTROL
# ------------------------------------------------------------------------------

COLOR_OK    = "#1f9d55"   # verde - acertó
COLOR_ERROR = "#d63031"   # rojo  - se equivocó
COLOR_BLANK = "#d63031"   # gris  - celda vacía (faltó completar)
COLOR_INVALID      = "#f39c12"  # naranja - item inválido (descripción basura, revisar)
COLOR_BOT_MISMATCH = "#e67e22"  # naranja oscuro - error por BOT en Initial Catalog
# ------------------------------------------------------------------------------
# DETECCIÓN DE ITEMS INVÁLIDOS
# ------------------------------------------------------------------------------
LONGITUD_MINIMA_ITEM = 3   # items con 3 chars o menos -> inválido

PATRONES_ITEM_INVALIDO = [
    r"^\s*[\d.,\s]+\s*$",   # solo dígitos, puntos, comas y espacios
    r"^\s*[-_*]+\s*$",      # solo símbolos como ---, ___, ***
]

# ------------------------------------------------------------------------------
# PALABRAS QUE SE BUSCAN SOLO COMO PALABRA COMPLETA (sin palabras pegadas)
# ------------------------------------------------------------------------------
# Las palabras listadas aquí SOLO matchean como palabra completa (con plurales),
# NUNCA dentro de palabras pegadas. Útil para palabras cortas que dan falsos
# positivos como "water" en "watermelon", "ice" en "rice", etc.
PALABRAS_SOLO_EXACTAS = [
    "water",        # watermelon, watercress
    "ice",          # rice, juice, dice, slice
    "tea",          # 
    "oil",          # broil, foil
    "bag",          # bagel
    "bar",          # barrel
    "can",          # candy, cancel
    "chip",         # chipotle
    "nut",          # nutmeg, peanut
    "ham", "hen",        # hamster
    "rib",          # ribbon
    "pie",          # piece
    "go",           # mango, gourmet
    "hk",           # sigla muy corta
    "gng",          # sigla muy corta
    "org",          # organize
    "stk",          # sigla
    "fee",          # feet, coffee
    "egg",          # eggplant
    "rice", "rub", "bbq", "cod","bh", "hog",
    "straw" # se busca exacta
]

# ------------------------------------------------------------------------------
# CATEGORÍAS POSIBLES (no tocar)
# ------------------------------------------------------------------------------
CAT_BANNED            = "Banned"
CAT_LOCAL_MEAT        = "Local Meat"
CAT_LOCAL             = "Local"
CAT_NON_CONTRACTED    = "Non-contracted"
CAT_PPI               = "PPI"
CAT_INITIAL_CATALOG   = "Initial Catalog"
CAT_DAIRY             = "Dairy"
CAT_GRAB_AND_GO       = "Grab and Go"
CAT_DAIRY_GNG         = "Dairy/GnG"
CAT_REVISAR           = "⚠️ Revisar"   # items con descripción inválida

# Validar que las reglas específicas usen divisiones existentes
_validar_reglas_especificas()
