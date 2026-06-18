"""
================================================================================
MÓDULO DE CLASIFICACIÓN
================================================================================
Aplica las reglas de negocio para clasificar cada producto en una categoría
y luego determinar R/E para cada una de las divisiones.

Orden de las reglas (importante):
  1. Banned                 -> R en todas las divisiones
  2. Local + es carne (IA)  -> R en todas
  3. Local + NO es carne    -> E en todas
  4. Non-contracted         -> R en todas
  5. PPI                    -> E en todas (incluye procesados)
  6. Initial Catalog (por descarte) -> Algunas divisiones se exponen
                               automáticamente, otras dependen del archivo BOT.

Detección de palabras:
  - Búsqueda case-insensitive con límite de palabra (\b)
  - Plurales automáticos: "muffin" matchea también "muffins", "box" matchea "boxes"
  - Palabras pegadas: si una palabra del producto tiene 10+ caracteres y la
    keyword tiene 5+ caracteres, también busca como substring.
    Ej: "MUSHROOMSLICED" contiene "sliced" -> match
================================================================================
"""

import json
import re
from pathlib import Path
from functools import lru_cache
import config


# Carga las categorías una sola vez al importar el módulo.
# Intenta BD primero; si falla o está vacía, usa el archivo local como fallback.
def _cargar_categorias() -> dict:
    try:
        import db as _db
        data = _db.cargar_categorias()
        if data:
            return data
    except Exception:
        pass
    _cats_path = Path(__file__).parent / "categorias.json"
    with open(_cats_path, "r", encoding="utf-8") as f:
        return json.load(f)


CATEGORIAS = _cargar_categorias()


# ------------------------------------------------------------------------------
# Configuración de detección de palabras pegadas
# ------------------------------------------------------------------------------
LONGITUD_MIN_PALABRA_PEGADA = 10
LONGITUD_MIN_KEYWORD_SUBSTRING = 5


# ------------------------------------------------------------------------------
# CACHÉ DE REGEX COMPILADAS (mejora performance significativamente)
# ------------------------------------------------------------------------------
@lru_cache(maxsize=4096)
def _compilar_patron(palabra_low: str):
    """Compila y cachea el patrón regex para una palabra dada."""
    return re.compile(
        r"(?<![a-z])" + re.escape(palabra_low) + r"(?:es|s)?(?![a-z])"
    )


@lru_cache(maxsize=4096)
def _compilar_patron_singular(palabra_low: str):
    """Compila y cachea el patrón para la forma singular de una palabra plural."""
    if palabra_low.endswith("es") and len(palabra_low) > 4:
        sin_es = palabra_low[:-2]
        return re.compile(
            r"(?<![a-z])" + re.escape(sin_es) + r"(?:es|s)?(?![a-z])"
        )
    elif palabra_low.endswith("s") and len(palabra_low) > 3:
        sin_s = palabra_low[:-1]
        return re.compile(
            r"(?<![a-z])" + re.escape(sin_s) + r"(?:es|s)?(?![a-z])"
        )
    return None


# Caché lazy del set de palabras solo exactas (acceso O(1) en vez de O(n))
_PALABRAS_SOLO_EXACTAS_SET = None


def _get_palabras_solo_exactas() -> set:
    global _PALABRAS_SOLO_EXACTAS_SET
    if _PALABRAS_SOLO_EXACTAS_SET is None:
        _PALABRAS_SOLO_EXACTAS_SET = set(
            p.lower() for p in getattr(config, "PALABRAS_SOLO_EXACTAS", [])
        )
    return _PALABRAS_SOLO_EXACTAS_SET


# Patrón para tokenizar texto en palabras (compilado una vez)
_PATRON_TOKENS = re.compile(r"[a-zA-Z]+")


# ------------------------------------------------------------------------------
# Funciones auxiliares de detección de palabras
# ------------------------------------------------------------------------------
def _es_palabra_solo_exacta(palabra_low: str) -> bool:
    """
    True si la palabra está en config.PALABRAS_SOLO_EXACTAS.
    Recibe la palabra YA en minúscula (optimización).
    """
    return palabra_low in _get_palabras_solo_exactas()


def _contiene_palabra(texto: str, palabra: str) -> bool:
    """
    True si la palabra (o su plural) aparece en el texto como palabra completa.
    Optimizado con regex compiladas y cacheadas.
    """
    if not texto or not palabra:
        return False

    texto_low = texto.lower()
    palabra_low = palabra.lower()

    # Wildcard de prefijo: "micro*" matchea microgreens, microherb, etc.
    if palabra_low.endswith("*"):
        prefijo = re.escape(palabra_low[:-1])
        return bool(re.search(r"(?<![a-z])" + prefijo, texto_low))

    # Wildcard de sufijo: "*org" matchea ESCAROLEORG, PINEAPPLEORG/C, etc.
    if palabra_low.startswith("*"):
        sufijo = re.escape(palabra_low[1:])
        return bool(re.search(sufijo + r"(?![a-z])", texto_low))

    # 1. Palabra completa con plural opcional (regex cacheada)
    if _compilar_patron(palabra_low).search(texto_low):
        return True

    # 2. Forma singular si la keyword viene en plural
    patron_sing = _compilar_patron_singular(palabra_low)
    if patron_sing is not None and patron_sing.search(texto_low):
        return True

    # 3. Búsqueda como substring dentro de palabras LARGAS y pegadas
    if _es_palabra_solo_exacta(palabra_low):
        return False

    if len(palabra_low) >= LONGITUD_MIN_KEYWORD_SUBSTRING:
        for token in _PATRON_TOKENS.findall(texto_low):
            if len(token) >= LONGITUD_MIN_PALABRA_PEGADA and palabra_low in token:
                return True

    return False


def _contiene_palabra_estricta(texto: str, palabra: str) -> bool:
    """
    Versión MÁS ESTRICTA de _contiene_palabra: solo busca como palabra completa
    (con plurales), pero NO busca dentro de palabras pegadas.

    Útil para reglas específicas donde no queremos falsos positivos.
    Por ejemplo, "flower" NO debe matchear "cauliflower" o "sunflower".
    """
    if not texto or not palabra:
        return False

    texto_low = texto.lower()
    palabra_low = palabra.lower()

    # Wildcards (mismo comportamiento que _contiene_palabra)
    if palabra_low.endswith("*"):
        prefijo = re.escape(palabra_low[:-1])
        return bool(re.search(r"(?<![a-z])" + prefijo, texto_low))
    if palabra_low.startswith("*"):
        sufijo = re.escape(palabra_low[1:])
        return bool(re.search(sufijo + r"(?![a-z])", texto_low))

    # Usa los compiladores cacheados (igual que _contiene_palabra, sin substring)
    if _compilar_patron(palabra_low).search(texto_low):
        return True
    patron_sing = _compilar_patron_singular(palabra_low)
    if patron_sing is not None and patron_sing.search(texto_low):
        return True

    return False


def _contiene_alguna_estricta(texto: str, lista_palabras: list) -> bool:
    """Versión estricta de _contiene_alguna (sin palabras pegadas)."""
    return any(_contiene_palabra_estricta(texto, p) for p in lista_palabras)


def _contiene_alguna(texto: str, lista_palabras: list) -> bool:
    """True si el texto contiene al menos una palabra de la lista."""
    return any(_contiene_palabra(texto, p) for p in lista_palabras)


def _es_excepcion(texto: str) -> bool:
    """
    Verifica si el item está en la lista de excepciones (los ⚠️ Care).
    Si lo está, NO se clasifica como Non-contracted.
    """
    excepciones = CATEGORIAS.get("_excepciones_cuidado", {}).get(
        "no_clasificar_si_contiene", []
    )
    return _contiene_alguna(texto, excepciones)


def _es_formato_con_produce_fresco(item: str) -> bool:
    """
    True si el item contiene un keyword de formato/empaque (bag, tray, etc.) Y
    también un keyword de produce fresco. En ese caso, no debe ser Non-Contracted.
    """
    config_exc = CATEGORIAS.get("_excepciones_formato_produce", {})
    formatos = config_exc.get("formatos", [])
    produce = config_exc.get("produce_fresco", [])
    if not formatos or not produce:
        return False
    return _contiene_alguna(item, formatos) and _contiene_alguna(item, produce)


# ------------------------------------------------------------------------------
# Detectores de cada categoría
# ------------------------------------------------------------------------------
def es_banned(item: str) -> bool:
    # "microwavable" es Initial Catalog, no Banned (aunque micro* esté en la lista)
    if _contiene_palabra(item, "microwavable"):
        return False
    # Brussels/Brussel Sprouts no son Banned aunque "sprouts" esté en la lista
    if _contiene_palabra(item, "brussel"):
        return False
    return _contiene_alguna(item, CATEGORIAS["banned"])


def es_local(item: str) -> bool:
    return _contiene_palabra(item, "local") or _contiene_palabra(item, "lcl")


def es_non_contracted(item: str) -> bool:
    """
    Recorre todas las subcategorías de non_contracted.

    REGLA DE PRIORIDAD:
    Las palabras de 'preservation' (organic, frozen, dried, canned, etc.)
    son INDICADORES FUERTES que NO se pueden ignorar con excepciones.
    Si un item tiene 'organic', SIEMPRE es Non-contracted, aunque esté en
    la lista de _excepciones_cuidado.

    Ejemplo: "Vegetable Blend Mirepoix Organic" → Non-contracted (gana 'organic')
    Ejemplo: "Vegetable Blend Mirepoix"          → no Non-contracted (excepción válida)
    """
    # Si tiene palabras de preservation (organic, frozen, etc.), gana siempre
    palabras_preservation = CATEGORIAS["non_contracted"].get("preservation", [])
    if _contiene_alguna(item, palabras_preservation):
        return True

    # Para todas las demás subcategorías, las excepciones SÍ aplican
    if _es_excepcion(item):
        return False

    # Si es formato de empaque (bag, tray) + produce fresco → no es non-contracted
    if _es_formato_con_produce_fresco(item):
        return False

    for subcat, palabras in CATEGORIAS["non_contracted"].items():
        if subcat.startswith("_"):
            continue
        if subcat == "preservation":
            continue  # ya evaluado arriba
        if _contiene_alguna(item, palabras):
            return True
    return False


def es_ppi(item: str) -> bool:
    """
    PPI = Process Produce Items.
    Incluye basket (tofu, sauce, paste) y procesados (diced, sliced, etc.)
    """
    for subcat, palabras in CATEGORIAS["ppi"].items():
        if subcat.startswith("_"):
            continue
        if _contiene_alguna(item, palabras):
            return True
    return False


def es_dairy(item: str) -> bool:
    """
    True si el item contiene una palabra clave de Dairy.
    Usa búsqueda ESTRICTA (sin palabras pegadas) para evitar falsos positivos.
    """
    palabras = getattr(config, "PALABRAS_DAIRY", [])
    return _contiene_alguna_estricta(item, palabras)


def es_grab_and_go(item: str) -> bool:
    """
    True si el item contiene una palabra clave de Grab and Go.
    Usa búsqueda ESTRICTA (sin palabras pegadas) porque algunas keywords son
    siglas cortas (GO, Hk, GnG) que NO deben buscarse dentro de palabras pegadas.
    """
    palabras = getattr(config, "PALABRAS_GRAB_AND_GO", [])
    return _contiene_alguna_estricta(item, palabras)


def _normalizar_id(valor) -> str:
    """
    Convierte un ID (Supplier ID, SKU, etc.) a string limpio.
    Misma lógica que utils._normalizar_id:
      - 1103541.0  ->  "1103541"  (quita el .0 que pandas pone a los floats)
      - "1103541 " ->  "1103541"  (quita espacios)
      - NaN/None   ->  ""
    """
    if valor is None:
        return ""
    try:
        import pandas as pd
        if pd.isna(valor):
            return ""
    except Exception:
        pass
    s = str(valor).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


# Alias para compatibilidad hacia atrás
_normalizar_supplier_id = _normalizar_id


def es_invalido(item: str) -> bool:
    """
    True si el item tiene una descripción 'basura' que no se puede clasificar:
      - Es un número puro (5, 66.5, 123)
      - Tiene LONGITUD_MINIMA_ITEM o menos caracteres después de strip
      - Coincide con algún patrón de PATRONES_ITEM_INVALIDO
    """
    if not isinstance(item, str):
        return True
    s = item.strip()
    if not s:
        return False  # los blancos se manejan aparte (no es "inválido", es vacío)

    # Longitud mínima
    if len(s) <= getattr(config, "LONGITUD_MINIMA_ITEM", 3):
        return True

    # Patrones regex
    patrones = getattr(config, "PATRONES_ITEM_INVALIDO", [])
    for patron in patrones:
        try:
            if re.match(patron, s):
                return True
        except re.error:
            pass

    return False


# ------------------------------------------------------------------------------
# Clasificador principal
# ------------------------------------------------------------------------------
def clasificar_categoria(item: str, es_carne_func=None, supplier_id=None) -> str:
    """
    Devuelve la categoría del item siguiendo el ORDEN exacto de las reglas.

    Args:
        item: nombre del producto (Item description)
        es_carne_func: función que recibe el nombre y devuelve True/False
        supplier_id: Supplier ID del producto (para la regla Dairy/GnG)
    """
    if not isinstance(item, str) or not item.strip():
        return config.CAT_INITIAL_CATALOG

    # 0. Item inválido (descripción basura: número puro, muy corto, etc.)
    # Va PRIMERO de todo: estos items no se clasifican normalmente.
    if es_invalido(item):
        return config.CAT_REVISAR

    # 1. Banned (PRIMERO, incluso antes de Local)
    if es_banned(item):
        return config.CAT_BANNED

    # 2. Local
    if es_local(item):
        if es_carne_func and es_carne_func(item):
            return config.CAT_LOCAL_MEAT
        return config.CAT_LOCAL

    # 2.5 Flower logic:
    #   (flow/flower) sin "edible" → Non-Contracted (R todas)
    #   (flow/flower) con "edible" → Initial Catalog (BOT decide; School Services
    #                                se fuerza a R via REGLAS_ESPECIFICAS_POR_DIVISION)
    _flor_excluidas = getattr(config, "PALABRAS_FLOR_EXCLUIDAS", [])
    _flor_keywords  = getattr(config, "PALABRAS_FLOR", [])
    if not _contiene_alguna_estricta(item, _flor_excluidas):
        if _contiene_alguna_estricta(item, _flor_keywords):
            if _contiene_palabra(item, "edible"):
                return config.CAT_INITIAL_CATALOG
            return config.CAT_NON_CONTRACTED

    # 3. Dairy / Grab and Go (depende del supplier)
    # Esta regla va ANTES de Non-contracted porque palabras como "milk" están
    # en non_contracted.dairy y la atraparían primero.
    sid = _normalizar_supplier_id(supplier_id)
    suppliers = getattr(config, "SUPPLIERS_DAIRY_GNG", {})
    es_d = es_dairy(item)
    es_gng = es_grab_and_go(item)

    if sid in suppliers and (es_d or es_gng):
        permisos = suppliers[sid]
        permite_d = permisos.get("dairy", False) and es_d
        permite_gng = permisos.get("grab_and_go", False) and es_gng

        # Si el supplier permite AMBOS y el item matchea ambos -> Dairy/GnG
        if permite_d and permite_gng:
            return config.CAT_DAIRY_GNG
        if permite_d:
            return config.CAT_DAIRY
        if permite_gng:
            return config.CAT_GRAB_AND_GO
        # El supplier dice "No" para lo que matchea -> forzar a Non-contracted
        return config.CAT_NON_CONTRACTED

    # Si el supplier NO está en la lista pero el item matchea Dairy/GnG, igual
    # debe clasificarse como Non-contracted (ya que estos son productos
    # procesados y por defecto deberían restringirse). Esto es coherente con
    # tu ejemplo: "milk con supplier no listado -> non contracted -> R".
    if es_d or es_gng:
        return config.CAT_NON_CONTRACTED

    # 4. Non-contracted
    if es_non_contracted(item):
        return config.CAT_NON_CONTRACTED

    # 5. PPI (incluye procesados)
    if es_ppi(item):
        return config.CAT_PPI

    # 6. Por descarte: Initial Catalog. BOT decide la exposición por división.
    return config.CAT_INITIAL_CATALOG


# ------------------------------------------------------------------------------
# Determina R/E por división según la categoría y el archivo BOT
# ------------------------------------------------------------------------------
def calcular_re_por_division(categoria: str, sku, skus_bot: set, item: str = "",
                              supplier_id=None) -> dict:
    """
    Devuelve un diccionario {division: 'R' o 'E'} para todas las divisiones,
    basándose en:
      1. La categoría del producto (Banned, Local, Non-contracted, PPI, etc.)
      2. Si el SKU está en el archivo BOT (para Initial Catalog)
      3. Las REGLAS_ESPECÍFICAS_POR_DIVISION que coincidan con el item
         (overrides finales)
      4. Las REGLAS_ESPECÍFICAS_POR_SUPPLIER si el supplier_id coincide
         (overrides finales por supplier)

    Args:
        categoria: la categoría ya calculada
        sku: número del producto
        skus_bot: conjunto (set) de SKUs presentes en el archivo BOT
        item: nombre del producto, para evaluar las reglas específicas
        supplier_id: ID del supplier, para evaluar reglas por supplier
    """
    resultado = {}

    # Caso especial: items inválidos -> devolver "INVALID" en todas
    # (utils.py los manejará para mostrarlos en naranja sin compararlos)
    if categoria == config.CAT_REVISAR:
        for div in config.DIVISIONES:
            resultado[div] = "INVALID"
        return resultado

    if categoria == config.CAT_BANNED:
        valor = "R"
    elif categoria == config.CAT_LOCAL_MEAT:
        valor = "R"
    elif categoria == config.CAT_LOCAL:
        valor = "E"
    elif categoria == config.CAT_DAIRY:
        valor = "E"
    elif categoria == config.CAT_GRAB_AND_GO:
        valor = "E"
    elif categoria == config.CAT_DAIRY_GNG:
        valor = "E"
    elif categoria == config.CAT_NON_CONTRACTED:
        valor = "R"
    elif categoria == config.CAT_PPI:
        valor = "E"
    else:
        valor = None  # Initial Catalog -> tratamiento especial

    if valor is not None:
        for div in config.DIVISIONES:
            resultado[div] = valor
    else:
        # ---- Initial Catalog ----
        for div in config.DIVISIONES_AUTO_EXPUESTAS:
            resultado[div] = "E"

        sku_str = _normalizar_supplier_id(sku)
        en_bot = sku_str in skus_bot
        for div in config.DIVISIONES_REQUIEREN_BOT:
            resultado[div] = "E" if en_bot else "R"

    # ---- Aplicar REGLAS ESPECÍFICAS POR DIVISIÓN (override final) ----
    # Usamos búsqueda ESTRICTA (sin palabras pegadas) para evitar falsos
    # positivos como "cauliflower" matcheando "flower".
    if item:
        reglas = getattr(config, "REGLAS_ESPECIFICAS_POR_DIVISION", [])
        for regla in reglas:
            palabras = regla.get("palabras_clave", [])
            if not _contiene_alguna_estricta(item, palabras):
                continue
            # Condición AND opcional: todas las palabras en "palabras_todas" deben estar presentes
            palabras_todas = regla.get("palabras_todas", [])
            if palabras_todas and not all(
                _contiene_palabra_estricta(item, p) for p in palabras_todas
            ):
                continue
            # El item coincide con esta regla -> aplicar overrides
            for div in regla.get("divisiones_restringidas", []):
                if div in resultado:
                    resultado[div] = "R"
            for div in regla.get("divisiones_expuestas", []):
                if div in resultado:
                    resultado[div] = "E"

    # ---- Aplicar REGLAS ESPECÍFICAS POR SUPPLIER (override final) ----
    # Si el supplier_id está en alguna regla, forzar a "R" todas las divisiones
    # EXCEPTO las listadas en "divisiones_normales" (que mantienen su valor
    # según la clasificación estándar).
    # No se aplica a items INVALID (se preservan tal cual).
    sid_norm = _normalizar_supplier_id(supplier_id)
    if sid_norm and categoria != config.CAT_REVISAR:
        reglas_supplier = getattr(config, "REGLAS_ESPECIFICAS_POR_SUPPLIER", [])
        for regla in reglas_supplier:
            ids_normalizados = {
                _normalizar_supplier_id(s) for s in regla.get("supplier_ids", [])
            }
            if sid_norm not in ids_normalizados:
                continue
            divisiones_normales = set(regla.get("divisiones_normales", []))
            # Forzar "R" en todas las divisiones que NO sean "normales"
            for div in config.DIVISIONES:
                if div not in divisiones_normales:
                    resultado[div] = "R"
            # Si la regla fuerza exposición sin BOT, las divisiones_normales
            # quedan en "E" SOLO para Initial Catalog (no para Banned, Non-contracted, etc.)
            if regla.get("forzar_expuesto_en_normales") and categoria == config.CAT_INITIAL_CATALOG:
                for div in divisiones_normales:
                    if div in resultado:
                        resultado[div] = "E"

    # ---- Aplicar EXCEPCIONES POR SKU + SUPPLIER (override más específico, último) ----
    if sid_norm and categoria != config.CAT_REVISAR:
        sku_norm = _normalizar_supplier_id(sku)
        excepciones = getattr(config, "EXCEPCIONES_POR_SKU_SUPPLIER", [])
        for exc in excepciones:
            if _normalizar_supplier_id(exc.get("supplier_id", "")) != sid_norm:
                continue
            skus_exc = {_normalizar_supplier_id(s) for s in exc.get("skus", [])}
            if sku_norm not in skus_exc:
                continue
            divs = exc.get("divisiones_expuestas") or list(config.DIVISIONES)
            for div in divs:
                if div in resultado:
                    resultado[div] = "E"

    # ---- Excepciones por Categoría + Supplier (override por categoría) ----
    if sid_norm and categoria != config.CAT_REVISAR:
        excepciones_cat = getattr(config, "EXCEPCIONES_POR_CATEGORIA_SUPPLIER", [])
        for exc in excepciones_cat:
            if _normalizar_supplier_id(exc.get("supplier_id", "")) != sid_norm:
                continue
            if categoria not in exc.get("categorias", []):
                continue
            divs = exc.get("divisiones_expuestas") or list(config.DIVISIONES)
            for div in divs:
                if div in resultado:
                    resultado[div] = "E"

    # ---- Excepciones por Keywords + Supplier (override por descripción con exclusiones) ----
    if sid_norm and categoria != config.CAT_REVISAR and item:
        excepciones_kw = getattr(config, "EXCEPCIONES_POR_KEYWORDS_SUPPLIER", [])
        for exc in excepciones_kw:
            if _normalizar_supplier_id(exc.get("supplier_id", "")) != sid_norm:
                continue
            palabras_todas = exc.get("palabras_todas", [])
            if not all(_contiene_palabra_estricta(item, p) for p in palabras_todas):
                continue
            palabras_excluidas = exc.get("palabras_excluidas", [])
            if any(_contiene_palabra_estricta(item, p) for p in palabras_excluidas):
                continue
            divs = exc.get("divisiones_expuestas") or list(config.DIVISIONES)
            for div in divs:
                if div in resultado:
                    resultado[div] = "E"

    return resultado
