"""Buffer de logs en memoria (ring) para el visor bonito en /logs.

Un handler de logging guarda los últimos ~800 registros con id incremental,
para que el visor pueda hacer 'tail' pidiendo solo lo nuevo (?after=<id>).
"""
import contextlib
import itertools
import logging
from collections import deque
from datetime import datetime, timezone

_BUFFER: deque = deque(maxlen=800)
_SEQ = itertools.count(1)


class RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        with contextlib.suppress(Exception):
            msg = self.format(record)
            # evita el spam de los visores: no registres su propio polling (/logs, /tool-usage)
            if record.name == "uvicorn.access" and ("/logs" in msg or "/tool-usage" in msg):
                return
            _BUFFER.append({
                "id": next(_SEQ),
                "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": msg,
            })


def install() -> None:
    """Engancha el ring handler SIN duplicar: al root (captura app/httpx/etc. por
    propagación) y a los loggers de uvicorn por separado (con propagate=False para
    que no se registren dos veces)."""
    h = RingHandler()
    h.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    if not any(isinstance(x, RingHandler) for x in root.handlers):
        root.addHandler(h)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        if not any(isinstance(x, RingHandler) for x in lg.handlers):
            lg.addHandler(h)
        lg.propagate = False   # evita el doble registro (handler en root + aquí)
        lg.setLevel(logging.INFO)


def recent(after: int = 0) -> list[dict]:
    return [r for r in list(_BUFFER) if r["id"] > after]
