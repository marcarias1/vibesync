"""Visor de logs: página bonita en /logs + datos incrementales en /logs/data."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.logbuffer import recent

router = APIRouter(tags=["logs"])

_HTML = Path(__file__).parent / "web" / "logs.html"


@router.get("/logs/data")
async def logs_data(after: int = 0, level: str = "ALL"):
    """Devuelve los logs con id > `after` (para 'tail' en vivo), filtrando por nivel."""
    rows = recent(after)
    last = rows[-1]["id"] if rows else after
    if level and level != "ALL":
        rows = [r for r in rows if r["level"] == level]
    return {"logs": rows[-500:], "last": last}


@router.get("/logs", include_in_schema=False)
async def logs_page():
    return FileResponse(str(_HTML))
