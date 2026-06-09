"""
================================================================================
GENERADOR DE HASHES DE CONTRASEÑA
================================================================================
Ejecuta este script para generar el hash bcrypt de una contraseña, que luego
debes pegar en .streamlit/secrets.toml.

Uso:
   python generar_hash.py

Ingresa la contraseña en texto plano, copia el hash que aparece, y pégalo
en el archivo secrets.toml en el campo "password" del usuario correspondiente.
================================================================================
"""

import streamlit_authenticator as stauth
from getpass import getpass


def main():
    print("=" * 60)
    print("  Generador de hash de contraseña")
    print("=" * 60)
    pwd = getpass("Ingresa la contraseña: ")
    if not pwd:
        print("⚠️ Contraseña vacía, abortando.")
        return

    # Hashea la contraseña con bcrypt
    hashed = stauth.Hasher.hash(pwd)

    print("\n✅ Hash generado (cópialo a secrets.toml):\n")
    print(hashed)
    print("\nEjemplo de uso en secrets.toml:")
    print("[credentials.usernames.juan]")
    print('name = "Juan Pérez"')
    print('email = "juan@empresa.com"')
    print(f'password = "{hashed}"')
    print()


if __name__ == "__main__":
    main()
