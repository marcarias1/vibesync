"""Cliente MongoDB async (PyMongo AsyncMongoClient, singleton por proceso)."""
from pymongo import AsyncMongoClient

from app.config import get_settings

_client: AsyncMongoClient | None = None


def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        # AsyncMongoClient NO es thread-safe: un cliente por event loop.
        _client = AsyncMongoClient(get_settings().mongo_uri, tz_aware=True)
    return _client


def get_db():
    return get_client()[get_settings().mongo_db]


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
