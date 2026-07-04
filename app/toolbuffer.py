"""Buffer en memoria del USO DE TOOLS y COMPLETIONS del agente, para el visor /tool-usage.

Cada evento es una `completion` (lo que decidió el LLM: qué tools llama, contenido) o un
`tool` (ejecución concreta con args, resultado y duración). Ring de ~500 como el de /logs.
"""
import itertools
from collections import deque
from datetime import datetime, timezone

_EVENTS: deque = deque(maxlen=500)
_SEQ = itertools.count(1)


def record(kind: str, name: str, **fields) -> None:
    """kind = 'completion' | 'tool'. fields: iter, duration_ms, tools, args, result, ok, content..."""
    _EVENTS.append({
        "id": next(_SEQ),
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "name": name,
        **fields,
    })


def recent(after: int = 0) -> list[dict]:
    return [e for e in list(_EVENTS) if e["id"] > after]
