"""Smoke tests de la API vía ASGI (httpx.AsyncClient + ASGITransport).

Se ejercita la app real con su lifespan (crea índices al arrancar). Si no hay
MongoDB escuchando, los tests se saltan en vez de fallar.
"""
import json
from pathlib import Path

import httpx
import pytest

import app.db.client as db_client
from app.config import get_settings
from app.ingest.importer import SKIP_REASONS
from app.main import app

FIXTURE = Path(__file__).parent / "fixtures" / "sample_history.json"


def _expected_valid(raw: list[dict]) -> int:
    """Aplica el mismo filtro de calidad que el importador para saber cuántas
    entradas deberían insertarse (>=30s, con URI y que no sea un skip)."""
    min_ms = get_settings().min_ms_played
    return sum(
        1
        for e in raw
        if e.get("ms_played", 0) >= min_ms
        and e.get("spotify_track_uri")
        and e.get("reason_end") not in SKIP_REASONS
    )


@pytest.fixture(autouse=True)
def _reset_client_singleton():
    """El cliente Mongo es un singleton por proceso atado a un event loop.
    Lo reseteamos alrededor de cada test para evitar reutilizar un cliente
    ligado a un loop ya cerrado (pytest-asyncio usa un loop por test)."""
    db_client._client = None
    yield
    db_client._client = None


async def _mongo_up() -> bool:
    """Comprueba que Mongo responde; si no, el test se salta."""
    try:
        db = db_client.get_db()
        await db.command("ping")
        return True
    except Exception:
        return False


async def test_health_ok():
    async with app.router.lifespan_context(app):
        if not await _mongo_up():
            pytest.skip("MongoDB no disponible")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "db" in body


async def test_import_streaming_history():
    raw = json.loads(FIXTURE.read_text())
    expected = _expected_valid(raw)
    assert expected > 0  # el fixture debe tener alguna entrada válida

    async with app.router.lifespan_context(app):
        if not await _mongo_up():
            pytest.skip("MongoDB no disponible")

        # limpieza previa: los _id son deterministas, así garantizamos que
        # cuenten como inserciones (no duplicados) aunque se repita el test.
        db = db_client.get_db()
        await db["playback_history"].delete_many({"user_id": "u_api"})

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as ac:
            with FIXTURE.open("rb") as fh:
                r = await ac.post(
                    "/import/streaming-history",
                    data={"user_id": "u_api"},
                    files={"files": ("sample_history.json", fh, "application/json")},
                )

    assert r.status_code == 200, r.text
    body = r.json()
    # las de <30s y fwdbtn NO cuentan
    assert body["kept"] == expected
    assert body["inserted"] == expected
    assert body["total"] == len(raw)          # todas parsean bien
    assert body["duplicates"] == 0
