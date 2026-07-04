from app.security.crypto import decrypt, encrypt


def test_roundtrip():
    secret = "AQV...refresh-token-xyz"
    token = encrypt(secret)
    assert token != secret          # cifrado, no en claro
    assert decrypt(token) == secret


def test_ciphertext_varies():
    # Fernet incluye IV → dos cifrados del mismo texto difieren
    assert encrypt("hola") != encrypt("hola")
