"""
================================================================================
APLICACIÓN PRINCIPAL - STREAMLIT
================================================================================
Punto de entrada de la app. Maneja:
  - Login con streamlit-authenticator
  - Carga de archivos (catálogo + BOT)
  - Procesamiento con clasificador.py + ia_carne.py
  - Visualización de la tabla con modelo de control coloreado
  - Filtros interactivos
  - Descarga del Excel coloreado

Para correr localmente:
   streamlit run app.py
================================================================================
"""

import streamlit as st
import pandas as pd
import io as _io

import config
import utils
import auth
import ia_carne


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def _construir_resumen_por_persona(df: "pd.DataFrame", divisiones: list) -> "pd.DataFrame":
    """Agrupa df por persona y cuenta ok/error/blank/invalid por división."""
    filas = []
    for persona, df_p in df.groupby(config.COL_ASSIGN_PERSON, dropna=False):
        nombre = persona if pd.notna(persona) and str(persona).strip() else "(Unassigned)"
        ok  = sum((df_p[f"{div} (estado)"] == "ok").sum()    for div in divisiones)
        err = sum((df_p[f"{div} (estado)"] == "error").sum() for div in divisiones)
        blk = sum((df_p[f"{div} (estado)"] == "blank").sum() for div in divisiones)
        inv = (df_p["Categoria"] == config.CAT_REVISAR).sum()
        total = ok + err + blk
        filas.append({
            "Person":      nombre,
            "Products":    len(df_p),
            "Matches 🟢":  ok,
            "Errors 🔴":   err,
            "Blanks ⚪":   blk,
            "Invalid 🟠":  inv,
            "% Match":     round(ok / total * 100, 1) if total else 0,
        })
    return (
        pd.DataFrame(filas)
        .sort_values(by=["Errors 🔴", "Blanks ⚪"], ascending=False)
        .reset_index(drop=True)
    )


def _mostrar_tabla_resumen(df_r: "pd.DataFrame") -> None:
    """Renderiza la tabla de resumen por persona con barras de progreso."""
    max_err = max(df_r["Errors 🔴"].max(), 1)
    max_blk = max(df_r["Blanks ⚪"].max(), 1)
    max_inv = max(df_r["Invalid 🟠"].max(), 1)
    st.dataframe(
        df_r,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Products":   st.column_config.NumberColumn(format="%d"),
            "Matches 🟢": st.column_config.NumberColumn(format="%d"),
            "Errors 🔴":  st.column_config.ProgressColumn(format="%d",   min_value=0, max_value=int(max_err)),
            "Blanks ⚪":  st.column_config.ProgressColumn(format="%d",   min_value=0, max_value=int(max_blk)),
            "Invalid 🟠": st.column_config.ProgressColumn(format="%d",   min_value=0, max_value=int(max_inv)),
            "% Match":    st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
        },
    )


# ------------------------------------------------------------------------------
# Configuración de página
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Catalog Classifier",
    page_icon="📦",
    layout="wide",
)

# ------------------------------------------------------------------------------
# 1. Login
# ------------------------------------------------------------------------------
st.title("📦 Catalog Classifier")

authenticator, nombre_usuario = auth.login()

# Sidebar con info del usuario y botón de logout
with st.sidebar:
    st.success(f"👤 Session: **{nombre_usuario}**")
    authenticator.logout(location="sidebar")
    st.divider()

    # ------ AI Cache info ------
    n_cache = ia_carne.cargar_cache_inicial()
    st.caption(f"💾 AI cache: **{n_cache:,}** items learned")
    with st.expander("⚙️ Cache options"):
        st.caption(
            "The cache stores items already classified by the AI so they "
            "don't need to be queried again. Clear it only if you want "
            "to reclassify everything from scratch."
        )
        if st.button("🗑️ Clear AI cache", use_container_width=True):
            if ia_carne.limpiar_cache_persistente():
                st.success("Cache cleared. Refresh the page to apply.")
            else:
                st.error("Could not clear the cache.")
    st.divider()

# ------------------------------------------------------------------------------
# 2. Carga de archivos
# ------------------------------------------------------------------------------
st.header("1️⃣ - Upload Files")

col1, col2, col3 = st.columns(3)
with col1:
    archivo_catalogo = st.file_uploader(
        "📄 Catalog File",
        type=["xlsx", "xls"],
        key="catalogo",
        help="Excel with columns SKU nbr, Item description, Supplier name, "
             "Supplier ID, and the 7 divisions",
    )
with col2:
    archivo_bot = st.file_uploader(
        "🤖 BOT File",
        type=["xlsx", "xls"],
        key="bot",
        help="Excel with the SKU nbr column of approved products",
    )
with col3:
    archivo_exp = st.file_uploader(
        "📋 EXP File",
        type=["xlsx", "xls"],
        key="exp",
        help="Excel with columns Supplier SKU, Supplier ID, Division — "
             "items listed here must be 'E'; mismatches are flagged in red.",
    )

archivo_bot_char = st.file_uploader(
    "🥩 BOT Charcuterie File",
    type=["xlsx", "xls"],
    key="bot_char",
    help="Excel with PCC_NBR, SI_SKU, SI_DESCR columns. "
         "Non-contracted items found here will be exposed (E) in all divisions except SCHOOL SERVICES.",
)

if archivo_catalogo is None or archivo_bot is None or archivo_exp is None or archivo_bot_char is None:
    st.info("⬆️ Upload all four files to start processing.")
    st.stop()


# ------------------------------------------------------------------------------
# 3. Lectura y validación
# ------------------------------------------------------------------------------
with st.spinner("Reading files..."):
    df_catalogo = utils.leer_excel(archivo_catalogo.getvalue(), "Catálogo", skip_rows=config.SKIP_ROWS_CATALOGO)
    df_bot = utils.leer_excel(archivo_bot.getvalue(), "BOT", skip_rows=config.SKIP_ROWS_BOT)
    df_asign = utils.cargar_asignaciones()
    df_exp = utils.leer_excel(archivo_exp.getvalue(), "EXP", skip_rows=config.SKIP_ROWS_EXP) if archivo_exp is not None else None
    df_bot_char = utils.leer_excel(archivo_bot_char.getvalue(), "BOT Charcuterie", skip_rows=config.SKIP_ROWS_BOT_CHAR)

if df_catalogo.empty:
    st.error("The catalog is empty or could not be read.")
    st.stop()

faltantes_cat = utils.validar_columnas_catalogo(df_catalogo)
if faltantes_cat:
    st.error(
        f"❌ The catalog is missing these columns: **{', '.join(faltantes_cat)}**. "
        "Edit `config.py` if your Excel has different names."
    )
    st.stop()

faltantes_bot = utils.validar_columnas_bot(df_bot)
if faltantes_bot:
    st.error(
        f"❌ The BOT is missing the column: **{', '.join(faltantes_bot)}**. "
        "Edit `config.py` (COL_BOT_SKU) if your Excel has a different name."
    )
    st.stop()

if df_exp is not None:
    cols_req_exp = {config.COL_EXP_SKU, config.COL_EXP_SUPPLIER_ID, config.COL_EXP_DIVISION}
    if not cols_req_exp.issubset(df_exp.columns):
        faltantes_exp = cols_req_exp - set(df_exp.columns)
        st.error(
            f"❌ The EXP file is missing these columns: **{', '.join(faltantes_exp)}**. "
            "Edit `config.py` (COL_EXP_*) if your Excel has different names."
        )
        st.stop()

faltantes_bc = utils.validar_columnas_bot_char(df_bot_char)
if faltantes_bc:
    st.error(
        f"❌ The BOT Charcuterie is missing these columns: **{', '.join(faltantes_bc)}**. "
        "Edit `config.py` (COL_BOT_CHAR_*) if your Excel has different names."
    )
    st.stop()


# ------------------------------------------------------------------------------
# 4. Procesamiento (con caché en session_state para evitar reprocesar)
# ------------------------------------------------------------------------------
st.header("2️⃣ - Processing")

# Generamos una "huella" única de los archivos subidos. Si cambian los archivos,
# cambia la huella y reprocesamos. Si son los mismos archivos, usamos el caché.
huella_actual = (
    archivo_catalogo.name,
    archivo_catalogo.size,
    archivo_bot.name,
    archivo_bot.size,
    archivo_exp.name if archivo_exp is not None else None,
    archivo_exp.size if archivo_exp is not None else None,
    archivo_bot_char.name,
    archivo_bot_char.size,
)

# Si la huella cambió o no hay caché previo, procesar de nuevo
if (
    "huella_archivos" not in st.session_state
    or st.session_state["huella_archivos"] != huella_actual
    or "df_completo" not in st.session_state
):
    with st.spinner("Classifying products..."):
        df_completo = utils.procesar_catalogo(df_catalogo, df_bot, df_asign, df_exp=df_exp, df_bot_char=df_bot_char)
    # Guardar en session_state para no reprocesar al descargar
    st.session_state["df_completo"] = df_completo
    st.session_state["huella_archivos"] = huella_actual
    st.session_state["excel_descarga"] = None  # Resetear el excel cacheado
else:
    # Reutilizar el resultado de la sesión (no reprocesar)
    df_completo = st.session_state["df_completo"]

st.success(f"✅ Processed **{len(df_completo)}** products.")

# ------------------------------------------------------------------------------
# Tabs: Main Dashboard / Detailed Analysis
# ------------------------------------------------------------------------------
tab_main, tab_detail = st.tabs(["📊 Main Dashboard", "🔍 Detailed Analysis"])

with tab_main:
    # ------------------------------------------------------------------------------
    # 5. Métricas resumen
    # ------------------------------------------------------------------------------
    total = len(df_completo)
    total_celdas = total * len(config.DIVISIONES)
    aciertos = sum((df_completo[f"{div} (estado)"] == "ok").sum() for div in config.DIVISIONES)
    errores  = sum((df_completo[f"{div} (estado)"] == "error").sum() for div in config.DIVISIONES)
    blanks   = sum((df_completo[f"{div} (estado)"] == "blank").sum() for div in config.DIVISIONES)
    invalidos_celdas = sum((df_completo[f"{div} (estado)"] == "invalid").sum() for div in config.DIVISIONES)
    items_invalidos = (df_completo["Categoria"] == config.CAT_REVISAR).sum()

    # % de coincidencia se calcula sobre celdas válidas (excluye inválidos)
    celdas_validas = total_celdas - invalidos_celdas
    porc_acierto = (aciertos / celdas_validas * 100) if celdas_validas else 0

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total products", total)
    m2.metric("Matches🟢 ", aciertos)
    m3.metric("Errors 🔴", errores)
    m4.metric("Blanks ⚪", blanks)
    m5.metric("Invalid 🟠", items_invalidos, help="Items with garbage descriptions (pure numbers, very short text). Require manual review.")
    m6.metric("Match rate", f"{porc_acierto:.1f}%", help="Calculated over valid cells (excludes invalid items)")


    # ------------------------------------------------------------------------------
    # 5b. Resumen por persona
    # ------------------------------------------------------------------------------
    st.header("👥 Summary by Person")
    st.caption(
        "Matches, errors and blanks for each person who handled the catalog. "
        "Useful for feedback and training."
    )

    df_resumen = _construir_resumen_por_persona(df_completo, config.DIVISIONES)
    _mostrar_tabla_resumen(df_resumen)

    # Botón para descargar el resumen como Excel
    if st.session_state.get("buffer_resumen") is None or st.session_state.get("huella_archivos_resumen") != huella_actual:
        buffer_resumen = _io.BytesIO()
        with pd.ExcelWriter(buffer_resumen, engine="openpyxl") as writer:
            df_resumen.to_excel(writer, index=False, sheet_name="Summary")
        st.session_state["buffer_resumen"] = buffer_resumen.getvalue()
        st.session_state["huella_archivos_resumen"] = huella_actual

    st.download_button(
        label="⬇️ Download summary by person",
        data=st.session_state["buffer_resumen"],
        file_name="summary_by_person.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


    # ------------------------------------------------------------------------------
    # 6. Filtros
    # ------------------------------------------------------------------------------
    st.header("3️⃣ - Filters")

    f1, f2, f3, f4 = st.columns(4)

    with f1:
        distribuidores = ["All"] + sorted(
            df_completo[config.COL_SUPPLIER].dropna().astype(str).unique().tolist()
        )
        filtro_dist = st.selectbox("Supplier", distribuidores)

    with f2:
        categorias_disp = ["All"] + sorted(
            df_completo["Categoria"].dropna().unique().tolist()
        )
        filtro_cat = st.selectbox("Category", categorias_disp)

    with f3:
        personas_disp = ["All"] + sorted(
            df_completo[config.COL_ASSIGN_PERSON].dropna().astype(str).unique().tolist()
        )
        filtro_persona = st.selectbox("Person", personas_disp)

    with f4:
        filtro_div = st.selectbox(
            "Show only issues in division",
            ["None"] + list(config.DIVISIONES),
        )

    tipo_problema = st.radio(
        "Issue type",
        ["Errors and blanks", "Errors only 🔴", "Blanks only ⚪", "Invalid only 🟠"],
        horizontal=True,
        disabled=(filtro_div == "None"),
    )

    # Aplicar filtros
    df_filtrado = df_completo.copy()
    if filtro_dist != "All":
        df_filtrado = df_filtrado[df_filtrado[config.COL_SUPPLIER].astype(str) == filtro_dist]
    if filtro_cat != "All":
        df_filtrado = df_filtrado[df_filtrado["Categoria"] == filtro_cat]
    if filtro_persona != "All":
        df_filtrado = df_filtrado[df_filtrado[config.COL_ASSIGN_PERSON].astype(str) == filtro_persona]
    if filtro_div != "None":
        estado_col = f"{filtro_div} (estado)"
        if tipo_problema == "Errors only 🔴":
            df_filtrado = df_filtrado[df_filtrado[estado_col] == "error"]
        elif tipo_problema == "Blanks only ⚪":
            df_filtrado = df_filtrado[df_filtrado[estado_col] == "blank"]
        elif tipo_problema == "Invalid only 🟠":
            df_filtrado = df_filtrado[df_filtrado[estado_col] == "invalid"]
        else:  # Errors and blanks
            df_filtrado = df_filtrado[df_filtrado[estado_col].isin(["error", "blank"])]

    # ------------------------------------------------------------------------------
    # 7. Tabla principal con modelo de control
    # ------------------------------------------------------------------------------
    st.header("4️⃣ - Results Table")
    st.caption(
        "🟢 Green = the person got it right. "
        "🔴 Red = got it wrong. "
        "⚪ (—) = blank cell, missing entry. "
        "🟠 Orange = invalid item (Numerical Item description, requires manual review)."
    )

    df_vista = utils.construir_tabla_vista(df_filtrado)

    # Si hay muchísimas filas, ofrecer al usuario limitar la vista para no ahogar el navegador
    total_filas = len(df_vista)
    if total_filas > 500:
        st.warning(
            f"⚠️ **{total_filas:,}** rows filtered. "
            "Showing this many at once may slow down the browser. "
            "You can adjust how many to display below (the download includes ALL rows)."
        )
        limite = st.slider(
            "Rows to display on screen",
            min_value=500,
            max_value=min(total_filas, 50000),
            value=500,
            step=500,
        )
        df_vista_show = df_vista.head(limite)
        df_completo_show = df_filtrado.head(limite).reset_index(drop=True)
    else:
        df_vista_show = df_vista
        df_completo_show = df_filtrado.reset_index(drop=True)

    styler = utils.estilizar_tabla(df_vista_show, df_completo_show)

    st.dataframe(styler, use_container_width=True, height=600)


    # ------------------------------------------------------------------------------
    # 8. Descarga
    # ------------------------------------------------------------------------------
    st.header("5️⃣ - Download Classified Catalog")

    # Generar el Excel solo una vez por sesión (es costoso para 90k filas).
    # Si cambia el filtro, se regenera; si no, se reutiliza.
    huella_filtros = (filtro_dist, filtro_cat, filtro_persona, filtro_div, tipo_problema)
    if (
        st.session_state.get("excel_descarga") is None
        or st.session_state.get("huella_filtros") != huella_filtros
    ):
        with st.spinner("Preparing Excel file for download..."):
            excel_bytes = utils.exportar_excel_coloreado(df_filtrado.reset_index(drop=True))
        st.session_state["excel_descarga"] = excel_bytes
        st.session_state["huella_filtros"] = huella_filtros
    else:
        excel_bytes = st.session_state["excel_descarga"]

    st.download_button(
        label="⬇️ Download",
        data=excel_bytes,
        file_name="classified_catalog.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )


# ==============================================================================
# DETAILED ANALYSIS TAB
# ==============================================================================
with tab_detail:
    st.header("🔍 Detailed Analysis")
    st.caption(
        "Use the filters below to drill down by Person, Division and/or Category. "
        "Leave 'Person' empty to compare ALL people who worked on the selection."
    )

    # ----- Filtros -----
    d1, d2, d3 = st.columns(3)

    with d1:
        personas_d = ["(All people)"] + sorted(
            df_completo[config.COL_ASSIGN_PERSON].dropna().astype(str).unique().tolist()
        )
        filtro_d_persona = st.selectbox(
            "👤 Person",
            personas_d,
            key="detail_persona",
        )

    with d2:
        filtro_d_division = st.selectbox(
            "🏢 Division",
            ["(All divisions)"] + list(config.DIVISIONES),
            key="detail_division",
        )

    with d3:
        categorias_d = sorted(df_completo["Categoria"].dropna().unique().tolist())
        filtro_d_categoria = st.selectbox(
            "🏷️ Category",
            ["(All categories)"] + categorias_d,
            key="detail_categoria",
        )

    # ----- Construir el resumen aplicando filtros -----
    # 1) Filtro por persona y categoría afectan QUÉ PRODUCTOS se cuentan
    df_d = df_completo.copy()
    if filtro_d_persona != "(All people)":
        df_d = df_d[df_d[config.COL_ASSIGN_PERSON].astype(str) == filtro_d_persona]
    if filtro_d_categoria != "(All categories)":
        df_d = df_d[df_d["Categoria"] == filtro_d_categoria]

    # 2) Filtro por división afecta QUÉ CELDAS se cuentan
    if filtro_d_division != "(All divisions)":
        divisiones_a_contar = [filtro_d_division]
    else:
        divisiones_a_contar = list(config.DIVISIONES)

    # ----- Mensaje informativo de filtros activos -----
    filtros_activos = []
    if filtro_d_persona != "(All people)":
        filtros_activos.append(f"**{filtro_d_persona}**")
    if filtro_d_division != "(All divisions)":
        filtros_activos.append(f"Division: **{filtro_d_division}**")
    if filtro_d_categoria != "(All categories)":
        filtros_activos.append(f"Category: **{filtro_d_categoria}**")
    if filtros_activos:
        st.info("🔎 Filtered by: " + " | ".join(filtros_activos))

    st.divider()

    # ----- Mostrar tabla según haya o no persona seleccionada -----
    if filtro_d_persona == "(All people)":
        # ===== TABLA PIVOTE: TODAS las personas con su stats =====
        st.subheader("👥 Summary by Person")

        if len(df_d) == 0:
            st.warning("No products match the selected filters.")
        else:
            df_detail = _construir_resumen_por_persona(df_d, divisiones_a_contar)
            _mostrar_tabla_resumen(df_detail)

            # ----- Descarga del resumen filtrado -----
            buffer_d = _io.BytesIO()
            with pd.ExcelWriter(buffer_d, engine="openpyxl") as writer:
                df_detail.to_excel(writer, index=False, sheet_name="Detail")
            st.download_button(
                label="⬇️ Download filtered summary",
                data=buffer_d.getvalue(),
                file_name="detailed_summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_detail_all",
            )

    else:
        # ===== STATS de UNA persona específica =====
        st.subheader(f"📊 Stats for {filtro_d_persona}")

        if len(df_d) == 0:
            st.warning("No products match the selected filters.")
        else:
            productos = len(df_d)
            ok = sum((df_d[f"{div} (estado)"] == "ok").sum() for div in divisiones_a_contar)
            err = sum((df_d[f"{div} (estado)"] == "error").sum() for div in divisiones_a_contar)
            blk = sum((df_d[f"{div} (estado)"] == "blank").sum() for div in divisiones_a_contar)
            inv = (df_d["Categoria"] == config.CAT_REVISAR).sum()
            total_eval = ok + err + blk
            porc = (ok / total_eval * 100) if total_eval else 0

            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Products", productos)
            c2.metric("Matches 🟢", ok)
            c3.metric("Errors 🔴", err)
            c4.metric("Blanks ⚪", blk)
            c5.metric("Invalid 🟠", inv)
            c6.metric("% Match", f"{porc:.1f}%")

            # ----- Descarga: resumen de una persona como tabla de 1 fila -----
            df_one = pd.DataFrame([{
                "Person": filtro_d_persona,
                "Division": filtro_d_division,
                "Category": filtro_d_categoria,
                "Products": productos,
                "Matches": ok,
                "Errors": err,
                "Blanks": blk,
                "Invalid": inv,
                "% Match": round(porc, 1),
            }])
            buffer_one = _io.BytesIO()
            with pd.ExcelWriter(buffer_one, engine="openpyxl") as writer:
                df_one.to_excel(writer, index=False, sheet_name="Detail")
            st.download_button(
                label="⬇️ Download filtered summary",
                data=buffer_one.getvalue(),
                file_name="detailed_summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_detail_one",
            )

# ------------------------------------------------------------------------------
# Espacio para futuras gráficas
# ------------------------------------------------------------------------------
# Aquí podrás agregar luego:
#   st.header("📊 Gráficas")
#   - Distribución por categoría
#   - Discrepancias por distribuidor
#   - Heatmap de R/E por división
# ------------------------------------------------------------------------------
