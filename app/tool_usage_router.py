"""Visor de USO DE TOOLS + COMPLETIONS del agente (/tool-usage), estilo /logs pero
con el detalle de cada llamada: qué tool, con qué args, qué devolvió y cuánto tardó."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app import toolbuffer

router = APIRouter(tags=["tool-usage"])
_PAGE = Path(__file__).parent / "web" / "tool-usage.html"


@router.get("/tool-usage/data")
async def tool_usage_data(after: int = 0):
    ev = toolbuffer.recent(after)
    return {"events": ev, "last": ev[-1]["id"] if ev else after}


@router.get("/tool-usage", include_in_schema=False)
async def tool_usage_page():
    return FileResponse(str(_PAGE))
