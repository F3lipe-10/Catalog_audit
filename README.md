# 📦 Clasificador de Catálogo

Aplicación en Streamlit que clasifica artículos de un catálogo según reglas de
negocio (Banned, Local, Local Meat, Non-contracted, PPI, Processed Produce,
Initial Catalog) y compara contra las restricciones/exposiciones existentes
(modelo de control) para 7 divisiones.

## 🏗️ Estructura

```
proyecto_catalogo/
├── app.py                  # App principal de Streamlit
├── auth.py                 # Inicio de sesión
├── clasificador.py         # Reglas de clasificación
├── ia_carne.py             # Cliente Gemini (detección de carne)
├── utils.py                # Lectura Excel, exportación coloreada
├── config.py               # ⚙️ Nombres de columnas (EDITABLE)
├── categorias.json         # 📚 Diccionario de palabras (EDITABLE)
├── generar_hash.py         # Genera hash de contraseña
├── requirements.txt        # Dependencias
├── data/
│   └── asignaciones.xlsx   # Distribuidor → persona encargada
├── .streamlit/
│   ├── secrets.toml        # 🔐 Credenciales y API key (NO subir a git)
│   └── secrets.toml.example
├── .gitignore
└── README.md
```

## 🚀 Instalación local

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
   # Copia el ejemplo
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

4. **Generar hashes de contraseña:**
   ```bash
   python generar_hash.py
   # Pega el hash resultante en secrets.toml
   ```

5. **Conseguir API key de Gemini (gratis):**
   - Ve a https://aistudio.google.com/app/apikey
   - Crea una nueva API key
   - Pégala en `secrets.toml` bajo `[gemini] api_key = "..."`

6. **Crear archivo de asignaciones:**
   - Crea `data/asignaciones.xlsx` con dos columnas: `Supplier Name` y `Assigned to`

7. **Ejecutar la app:**
   ```bash
   streamlit run app.py
   ```


## ✏️ Cómo personalizar

- **Cambiar nombres de columnas:** edita `config.py`
- **Agregar/quitar palabras a una categoría:** edita `categorias.json`
- **Agregar usuarios:** corre `python generar_hash.py` y agrega un bloque
  `[credentials.usernames.NUEVO]` en `secrets.toml`
- **Cambiar colores R/E:** edita `COLOR_OK` y `COLOR_ERROR` en `config.py`

## 📝 Reglas de clasificación (orden)

1. **Banned** → R en todas las divisiones
2. **Local + es carne** (consulta IA) → R en todas
3. **Local + no es carne** → E en todas
4. **Non-contracted** → R en todas
5. **PPI** → E en todas
6. **Processed Produce** → R en todas
7. **Initial Catalog** (por descarte):
   - Airline lounges, Centerplate, School services → E automáticamente
   - Corporate services, Universities, Hospitals, Senior living → E si está en BOT, R si no
