"""Fixtures. Configura env ANTES de importar la app y crea un cliente Mongo fresco
por test (evita problemas de event loop con el singleton)."""
import os

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

# --- entorno de test (debe ir antes de importar app.config) --------------- #
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())
os.environ.setdefault(
    "MONGO_URI",
    os.environ.get("MONGO_TEST_URI", "mongodb://127.0.0.1:27020/?directConnection=true"),
)
os.environ.setdefault("MONGO_DB", "vibesync_test")

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

_TEST_COLLECTIONS = ["playback_history", "user_tracks_vibe", "tracks", "artists", "playlists"]


@pytest_asyncio.fixture
async def db():
    """Cliente Mongo fresco; salta el test si no hay Mongo escuchando."""
    from pymongo import AsyncMongoClient

    s = get_settings()
    client = AsyncMongoClient(s.mongo_uri, tz_aware=True, serverSelectionTimeoutMS=1500)
    try:
        await client.admin.command("ping")
    except Exception:
        await client.close()
        pytest.skip("MongoDB no disponible en %s" % s.mongo_uri)
    database = client[s.mongo_db]
    for c in _TEST_COLLECTIONS:
        await database[c].delete_many({})
    yield database
    await client.close()
