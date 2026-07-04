"""Cifrado de secretos en reposo (refresh tokens de Spotify) con Fernet."""
from cryptography.fernet import Fernet

from app.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().fernet_key
    if not key:
        raise RuntimeError("FERNET_KEY no configurada (genera una con Fernet.generate_key())")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
