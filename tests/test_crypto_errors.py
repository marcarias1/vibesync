"""Verifica que crypto lanza RuntimeError si FERNET_KEY está vacía."""
import pytest

import app.security.crypto as crypto
from app.config import Settings


def test_encrypt_sin_fernet_key_lanza_runtimeerror(monkeypatch):
    # Sustituimos get_settings por uno que devuelve fernet_key vacía.
    # Usamos monkeypatch para no tocar la env global ni el cache real
    # (se restaura solo al terminar el test → no rompe otros tests).
    fake = Settings(fernet_key="")
    monkeypatch.setattr(crypto, "get_settings", lambda: fake)

    with pytest.raises(RuntimeError):
        crypto.encrypt("secreto")


def test_decrypt_sin_fernet_key_lanza_runtimeerror(monkeypatch):
    fake = Settings(fernet_key="")
    monkeypatch.setattr(crypto, "get_settings", lambda: fake)

    with pytest.raises(RuntimeError):
        crypto.decrypt("cualquier-token")
