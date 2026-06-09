"""
================================================================================
MÓDULO DE AUTENTICACIÓN
================================================================================
Maneja el inicio de sesión usando streamlit-authenticator.
Las credenciales se leen de .streamlit/secrets.toml (hasheadas con bcrypt).

Para agregar/cambiar usuarios:
  1. Genera el hash con: python generar_hash.py
  2. Pégalo en secrets.toml bajo [credentials.usernames.NOMBRE]
================================================================================
"""

import streamlit as st
import streamlit_authenticator as stauth


def _to_plain_dict(obj):
    """
    Convierte recursivamente un AttrDict de st.secrets a un dict normal.
    Es necesario porque streamlit-authenticator necesita escribir dentro
    del dict (para control de intentos fallidos) y st.secrets es read-only.
    """
    if hasattr(obj, "items"):
        return {k: _to_plain_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain_dict(x) for x in obj]
    return obj


def login():
    """
    Muestra la pantalla de login. Si el usuario se autentica correctamente,
    devuelve el authenticator y el nombre. Si no, detiene la app.
    """
    # Convierte los secrets a un dict normal (mutable) para evitar
    # el error "Secrets does not support item assignment"
    credentials = {
        "usernames": _to_plain_dict(st.secrets["credentials"]["usernames"])
    }

    authenticator = stauth.Authenticate(
        credentials,
        st.secrets["cookie"]["name"],
        st.secrets["cookie"]["key"],
        st.secrets["cookie"]["expiry_days"],
    )

    # Renderiza el formulario de login
    authenticator.login(location="main")

    auth_status = st.session_state.get("authentication_status")
    name = st.session_state.get("name")

    if auth_status is False:
        st.error("❌ Usuario o contraseña incorrectos")
        st.stop()
    elif auth_status is None:
        st.warning("👤 Por favor ingresa tus credenciales")
        st.stop()

    return authenticator, name