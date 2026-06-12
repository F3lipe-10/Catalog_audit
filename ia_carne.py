"""
================================================================================
MÓDULO IA - DETECCIÓN DE CARNE CON DEEPSEEK + CACHÉ PERSISTENTE
================================================================================
Usa la API de DeepSeek (V4-Flash) para clasificar productos.

ESTRATEGIA EN 5 PASOS para ahorrar requests:

  1. Si el item está en la tabla cache_carne de PostgreSQL (Supabase)
     -> usar valor guardado, sin IA.
  2. Si el nombre contiene una palabra OBVIA de carne (beef, chicken, etc.)
     -> carne directa, sin IA.
  3. Si el nombre contiene una palabra OBVIA de NO-carne (milk, juice, etc.)
     -> NO carne, sin IA.
  4. Caché de sesión: no se consulta dos veces el mismo producto en la misma
     sesión de Streamlit.
  5. Los productos restantes se agrupan en LOTES de 20 y se mandan a DeepSeek.
     LOS RESULTADOS SE GUARDAN EN BD automáticamente para no volver a
     consultarlos nunca más.

⚠️ La API key se lee de st.secrets["deepseek"]["api_key"] o variable
    DEEPSEEK_API_KEY.
================================================================================
"""

import os
import re
import json
import time
from functools import lru_cache
import streamlit as st
from openai import OpenAI
import config
import db


TAMANO_LOTE = 20


_PATRON_TOKENS = re.compile(r"[a-zA-Z]+")
# 8 (no 10 como en clasificador) para detectar más combinaciones cortas
# pegadas como "TUNAFISH" (8), "CRABCAKE" (8), "FISHSOUP" (8), etc.
LONGITUD_MIN_PALABRA_PEGADA = 8
# 4 (no 5 como en clasificador) para que palabras de 4 letras como "beef",
# "pork", "lamb", "tuna", "crab" detecten formas pegadas como "GROUNDBEEF".
LONGITUD_MIN_KEYWORD_SUBSTRING = 4

_PALABRAS_SOLO_EXACTAS_SET = None


def _get_palabras_solo_exactas() -> set:
    """Caché del set de palabras-solo-exactas (acceso O(1))."""
    global _PALABRAS_SOLO_EXACTAS_SET
    if _PALABRAS_SOLO_EXACTAS_SET is None:
        _PALABRAS_SOLO_EXACTAS_SET = set(
            p.lower() for p in getattr(config, "PALABRAS_SOLO_EXACTAS", [])
        )
    return _PALABRAS_SOLO_EXACTAS_SET


@lru_cache(maxsize=4096)
def _compilar_patron(palabra_low: str):
    """Compila y cachea el patrón regex para una palabra dada."""
    return re.compile(
        r"(?<![a-z])" + re.escape(palabra_low) + r"(?:es|s)?(?![a-z])"
    )


def _palabra_completa(texto: str, palabra: str) -> bool:
    """
    True si la palabra aparece en el texto como palabra completa (con plural),
    O dentro de una palabra LARGA pegada (cuando la keyword tiene 5+ chars
    y la palabra en el texto tiene 10+ chars).

    Replica el comportamiento de clasificador._contiene_palabra para que el
    pre-filtro de carne detecte items pegados como "BURRITOSAUSAGE",
    "GROUNDBEEF", "CHICKENSALAD", etc.
    """
    if not texto or not palabra:
        return False

    texto_low = texto.lower()
    palabra_low = palabra.lower()

    # 1. Palabra completa con plural opcional
    if _compilar_patron(palabra_low).search(texto_low):
        return True

    # 2. Palabras "solo exactas" (water, ice, egg, ham, etc.) NO se buscan pegadas
    if palabra_low in _get_palabras_solo_exactas():
        return False

    # 3. Substring dentro de palabras LARGAS pegadas
    if len(palabra_low) >= LONGITUD_MIN_KEYWORD_SUBSTRING:
        for token in _PATRON_TOKENS.findall(texto_low):
            if len(token) >= LONGITUD_MIN_PALABRA_PEGADA and palabra_low in token:
                return True

    return False


def _es_excepcion_no_carne(nombre: str) -> bool:
    """True si el item está en la lista de excepciones."""
    excepciones = getattr(config, "EXCEPCIONES_NO_CARNE", [])
    return any(_palabra_completa(nombre, e) for e in excepciones)


def _es_obvio_carne(nombre: str) -> bool:
    """True si contiene palabra obvia de carne. Las excepciones tienen prioridad."""
    if _es_excepcion_no_carne(nombre):
        return False
    return any(_palabra_completa(nombre, p) for p in config.PALABRAS_CARNE_OBVIAS)


def _es_obvio_no_carne(nombre: str) -> bool:
    """True si contiene palabra obvia de NO carne."""
    return any(_palabra_completa(nombre, p) for p in config.PALABRAS_NO_CARNE_OBVIAS)


# ============================================================================
# CACHÉ PERSISTENTE EN BASE DE DATOS
# ============================================================================

def cargar_cache_inicial() -> int:
    """Para que app.py muestre cuántos items hay en el caché al inicio."""
    return db.contar_cache_carne()


def limpiar_cache_persistente() -> bool:
    """
    Borra el caché de la BD y de la memoria.
    Mantiene el nombre original para que app.py no necesite cambios.
    """
    if "_cache_carne" in st.session_state:
        del st.session_state["_cache_carne"]
    return db.limpiar_cache_carne()


# ============================================================================
# CLIENTE DEEPSEEK
# ============================================================================

@st.cache_resource
def _get_cliente():
    """Inicializa el cliente de DeepSeek una sola vez."""
    api_key = None
    try:
        api_key = st.secrets["deepseek"]["api_key"]
    except Exception:
        api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    try:
        return OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            timeout=30.0,
            max_retries=2,
        )
    except Exception as e:
        print(f"[DeepSeek init error] {e}")
        return None


def _llamar_ia(cliente, prompt_sistema, prompt_usuario):
    """Llamada directa a la API de DeepSeek."""
    return cliente.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=2000,
    )


def _consultar_lote(productos: list, reintentar_individual: bool = True) -> dict:
    """Manda un lote de productos a DeepSeek. Devuelve {producto: bool}."""
    cliente = _get_cliente()
    if cliente is None or not productos:
        return {}

    lista_numerada = "\n".join(f'"{i+1}": "{p}"' for i, p in enumerate(productos))

    prompt_sistema = (
        "You are a food classifier. You must respond ONLY with a valid JSON "
        "object whose keys are the product numbers (as strings: '1', '2', ...) "
        "and whose values are booleans (true if the product is meat, false otherwise)."
    )

    prompt_usuario = f"""For each product in the numbered list below, decide if
it is any type of meat, poultry, fish, seafood, or meat-derived product
(ham, salami, sausage, bacon, hamburger, meatball, nuggets, deli meats,
fish products, etc.).

WHAT IS MEAT (return true):
- Beef, pork, lamb, veal, venison, bison, rabbit, goat
- Poultry: chicken, turkey, duck, quail
- Fish and seafood: salmon, tuna, shrimp, lobster, crab, oyster, etc.
- Processed meats: ham, bacon, sausage, salami, prosciutto, pepperoni, mortadella
- Prepared meat dishes: meatball, hamburger, nuggets, deli sandwiches with meat

WHAT IS NOT MEAT (return false):
- Dairy products: milk, yogurt, cheese, butter, cream
- Vegetables, fruits, grains, legumes
- Tofu and plant-based proteins
- Eggs (treated separately, NOT meat)
- Mushrooms, even when their name sounds like meat:
  * "Lobster mushroom" -> mushroom, NOT lobster
  * "Oyster mushroom" -> mushroom, NOT oyster
  * "Chicken of the woods" -> mushroom, NOT chicken
  * "Beefsteak mushroom" -> mushroom, NOT beef
  * "Hen of the woods" -> mushroom, NOT poultry
- Vegetables/fruits with meat-sounding names:
  * "Beefsteak tomato" -> tomato, NOT beef
  * "Lentil caviar" / "Black caviar lentils" -> lentils, NOT fish eggs
  * "Vegetable caviar" -> vegetables, NOT fish eggs
- Packaging terms (NOT seafood):
  * "Clamshell" / "Clamshells" -> plastic container, NOT clam

CRITICAL: When in doubt, look at the FULL product name. If the main item is
clearly a vegetable, fruit, mushroom, or non-meat food, return false even if
it contains a word that could refer to meat.

Products to classify ({len(productos)} total):
{lista_numerada}

Respond with a JSON object mapping each number to a boolean. Example for 3 products:
{{"1": true, "2": false, "3": true}}

You MUST include ALL {len(productos)} numbers from 1 to {len(productos)}."""

    try:
        respuesta = _llamar_ia(cliente, prompt_sistema, prompt_usuario)
        texto = respuesta.choices[0].message.content
        data = json.loads(texto)

        if not isinstance(data, dict):
            print(f"[DeepSeek batch] respuesta no es dict: {texto[:200]}")
            return {}

        resultados = {}
        faltantes = []
        for i, prod in enumerate(productos, start=1):
            clave = str(i)
            if clave in data and isinstance(data[clave], bool):
                resultados[prod] = data[clave]
            else:
                faltantes.append(prod)

        MAX_REINTENTOS_INDIVIDUALES = 5
        if faltantes and reintentar_individual:
            faltantes_a_reintentar = faltantes[:MAX_REINTENTOS_INDIVIDUALES]
            if len(faltantes) > MAX_REINTENTOS_INDIVIDUALES:
                print(f"[DeepSeek batch] {len(faltantes)} sin respuesta, "
                      f"reintentando solo {MAX_REINTENTOS_INDIVIDUALES}.")
            else:
                print(f"[DeepSeek batch] {len(faltantes)} sin respuesta, reintentando...")
            for prod in faltantes_a_reintentar:
                r = _consultar_lote([prod], reintentar_individual=False)
                if prod in r:
                    resultados[prod] = r[prod]
                time.sleep(getattr(config, "PAUSA_ENTRE_LOTES", 0.5))

        return resultados

    except json.JSONDecodeError as e:
        print(f"[DeepSeek batch] error de JSON: {e}")
        return {}
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "rate_limit" in error_msg.lower():
            espera = 10.0
            match = re.search(r"try again in (?:(\d+)m)?(\d+(?:\.\d+)?)s", error_msg)
            if match:
                minutos = int(match.group(1) or 0)
                segundos = float(match.group(2))
                espera = minutos * 60 + segundos + 1.0
                if espera > 60:
                    print(f"[DeepSeek batch] rate limit pide {espera:.0f}s, saltando.")
                    return {}
            print(f"[DeepSeek batch] rate limit, esperando {espera:.1f}s...")
            time.sleep(espera)
            try:
                respuesta = _llamar_ia(cliente, prompt_sistema, prompt_usuario)
                texto = respuesta.choices[0].message.content
                data = json.loads(texto)
                if isinstance(data, dict):
                    resultados = {}
                    for i, prod in enumerate(productos, start=1):
                        clave = str(i)
                        if clave in data and isinstance(data[clave], bool):
                            resultados[prod] = data[clave]
                    return resultados
            except Exception as e2:
                print(f"[DeepSeek batch] reintento también falló: {e2}")
            return {}
        print(f"[DeepSeek batch error]: {e}")
        return {}


def _get_cache_sesion():
    """Caché en memoria de la sesión actual."""
    if "_cache_carne" not in st.session_state:
        st.session_state["_cache_carne"] = {}
    return st.session_state["_cache_carne"]


def es_carne(nombre_producto: str) -> bool:
    """Versión individual. Usa caché persistente, pre-filtros y caché de sesión."""
    if not nombre_producto or not isinstance(nombre_producto, str):
        return False

    # 1. caché persistente (BD)
    cache_bd = db.cargar_cache_carne()
    if nombre_producto in cache_bd:
        return cache_bd[nombre_producto]

    # 2. pre-filtros
    if _es_obvio_no_carne(nombre_producto):
        return False
    if _es_obvio_carne(nombre_producto):
        return True

    # 3. caché de sesión
    cache_sesion = _get_cache_sesion()
    if nombre_producto in cache_sesion:
        return cache_sesion[nombre_producto]

    # 4. consultar IA y guardar
    resultado = _consultar_lote([nombre_producto])
    valor = resultado.get(nombre_producto, False)
    cache_sesion[nombre_producto] = valor
    db.guardar_lote_cache_carne({nombre_producto: valor})
    return valor


def precalentar_cache(items: list) -> dict:
    """
    Procesa una lista de items por LOTES con caché en 4 niveles.

    Orden de resolución para cada item:
      1. Caché persistente (disco) - GRATIS, instantáneo, persistente
      2. Pre-filtros locales       - GRATIS, instantáneo
      3. Caché de sesión           - GRATIS, instantáneo (solo esta sesión)
      4. DeepSeek (en lotes)       - Costo + tiempo

    Después de procesar, los items consultados a la IA se PERSISTEN
    automáticamente para no consultarlos nunca más en el futuro.
    """
    cache_bd = db.cargar_cache_carne()
    cache_sesion = _get_cache_sesion()
    resultados = {}
    ambiguos = []

    contadores = {
        "cache_bd": 0,
        "carne_local": 0,
        "no_carne_local": 0,
        "cache_sesion": 0,
        "ambiguos": 0,
    }

    for item in items:
        if not item:
            resultados[item] = False
            continue

        # 1. caché persistente (BD)
        if item in cache_bd:
            resultados[item] = cache_bd[item]
            contadores["cache_bd"] += 1
        # 2. pre-filtro no-carne
        elif _es_obvio_no_carne(item):
            resultados[item] = False
            cache_sesion[item] = False
            contadores["no_carne_local"] += 1
        # 3. pre-filtro carne
        elif _es_obvio_carne(item):
            resultados[item] = True
            cache_sesion[item] = True
            contadores["carne_local"] += 1
        # 4. caché de sesión (acumula durante la sesión)
        elif item in cache_sesion:
            resultados[item] = cache_sesion[item]
            contadores["cache_sesion"] += 1
        else:
            ambiguos.append(item)
            contadores["ambiguos"] += 1

    # Si no hay ambiguos, ¡no hace falta llamar a la IA!
    if contadores["ambiguos"] == 0:
        st.success(
            f"✅ All items classified WITHOUT calling AI! "
            f"(database cache: {contadores['cache_bd']}, "
            f"pre-filters: {contadores['carne_local'] + contadores['no_carne_local']}, "
            f"session cache: {contadores['cache_sesion']})"
        )
        return resultados

    # Procesar ambiguos en lotes
    lotes = [ambiguos[i:i + TAMANO_LOTE] for i in range(0, len(ambiguos), TAMANO_LOTE)]
    total_lotes = len(lotes)
    fallos = 0
    productos_via_ia = 0
    fallos_seguidos = 0
    MAX_FALLOS_SEGUIDOS = 3
    items_nuevos_para_persistir = {}  # se guarda al disco UNA sola vez al final

    progreso = st.progress(
        0,
        text=f"Querying DeepSeek in batches (0/{total_lotes} batches, "
             f"{contadores['ambiguos']} ambiguous products)..."
    )

    detenido_temprano = False
    for i, lote in enumerate(lotes, start=1):
        respuesta = _consultar_lote(lote)
        if respuesta:
            for prod, valor in respuesta.items():
                resultados[prod] = valor
                cache_sesion[prod] = valor
                items_nuevos_para_persistir[prod] = valor
                productos_via_ia += 1
            fallos_seguidos = 0
        else:
            for prod in lote:
                resultados[prod] = False
                fallos += 1
            fallos_seguidos += 1

        progreso.progress(
            i / total_lotes,
            text=f"Querying DeepSeek: batch {i}/{total_lotes} "
                 f"(AI: {productos_via_ia}, failures: {fallos})"
        )

        if fallos_seguidos >= MAX_FALLOS_SEGUIDOS:
            print(f"[DeepSeek] {MAX_FALLOS_SEGUIDOS} batches failed in a row. Stopping.")
            for lote_restante in lotes[i:]:
                for prod in lote_restante:
                    resultados[prod] = False
                    fallos += 1
            detenido_temprano = True
            break

        if i < total_lotes:
            time.sleep(getattr(config, "PAUSA_ENTRE_LOTES", 0.3))

    progreso.empty()

    # PERSISTIR APRENDIZAJE EN BD (UNA SOLA escritura para eficiencia)
    persistido_ok = False
    if items_nuevos_para_persistir:
        persistido_ok = db.guardar_lote_cache_carne(items_nuevos_para_persistir)

    if detenido_temprano:
        st.error(
            f"⚠️ DeepSeek failed in {MAX_FALLOS_SEGUIDOS} consecutive batches. "
            f"Remaining items marked as NOT meat. "
            f"Check API key/balance at https://platform.deepseek.com"
        )

    total = len(items)
    mensaje_ahorrado = (
        f"💾 Database cache hit: {contadores['cache_bd']} items "
        f"(saved AI calls!) | "
    ) if contadores["cache_bd"] > 0 else ""

    st.info(
        f"📊 Classification of {total} items: "
        f"{mensaje_ahorrado}"
        f"Pre-filters: {contadores['carne_local'] + contadores['no_carne_local']} | "
        f"Session cache: {contadores['cache_sesion']} | "
        f"AI: {productos_via_ia} "
        f"({total_lotes} request{'s' if total_lotes != 1 else ''} to DeepSeek)."
    )

    if items_nuevos_para_persistir and persistido_ok:
        st.success(
            f"💾 Learned {len(items_nuevos_para_persistir)} new items "
            f"(saved to database for future runs)."
        )

    if fallos > 0 and not detenido_temprano:
        st.warning(
            f"⚠️ DeepSeek failed on {fallos} products (marked as NOT meat). "
            f"Verify API key/balance at https://platform.deepseek.com"
        )

    return resultados
