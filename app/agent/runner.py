"""Bucle de tool-calling con validación + reparación de argumentos.

Si el LLM manda argumentos inválidos, se le devuelve el error como resultado de
la herramienta y se le da otra oportunidad (auto-reparación), sin romper la sesión.
"""
import json
import logging
import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from app import toolbuffer
from app.agent.llm import ChatResult, LLMClient

log = logging.getLogger(__name__)


def _truncate(obj, _maxlen: int = 4000):
    """Versión acotada del resultado para no guardar cosas gigantes en el buffer."""
    try:
        s = json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        return {"repr": str(obj)[:_maxlen]}
    return obj if len(s) <= _maxlen else {"_truncated": True, "preview": s[:_maxlen]}


def _short(v):
    return f"[{len(v)} items]" if isinstance(v, list) else str(v)[:40]


def _summary(result) -> str:
    if isinstance(result, dict):
        return ", ".join(f"{k}={_short(v)}" for k, v in list(result.items())[:4])[:160]
    return str(result)[:160]

SYSTEM_PROMPT = (
    "Eres un DJ predictivo experto. Usa las herramientas para consultar el perfil "
    "y la biblioteca del usuario y construir playlists coherentes. Evita mezclar "
    "underground con mainstream comercial."
)

Executor = Callable[[object], Awaitable[dict]]


def _tool_msg(tool_call_id: str, content: dict) -> dict:
    # ensure_ascii=False → el LLM recibe el español legible (no \uXXXX)
    return {"role": "tool", "tool_call_id": tool_call_id,
            "content": json.dumps(content, default=str, ensure_ascii=False)}


def _assistant_msg(res: ChatResult) -> dict:
    return {
        "role": "assistant",
        "content": res.content,
        "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
            for tc in res.tool_calls
        ],
    }


async def run_agent(
    llm: LLMClient,
    executors: dict[str, Executor],
    arg_models: dict[str, type[BaseModel]],
    user_message: str,
    *,
    tool_schemas: list[dict] | None = None,
    max_iters: int = 6,
    system: str = SYSTEM_PROMPT,
    result_holder: dict | None = None,
) -> str:
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]
    for step in range(max_iters):
        t0 = time.perf_counter()
        res = await llm.chat(messages, tool_schemas)
        dt = int((time.perf_counter() - t0) * 1000)
        tool_names = [tc.name for tc in res.tool_calls]
        toolbuffer.record("completion", "deepseek", iter=step + 1, duration_ms=dt,
                          tools=tool_names, content=(res.content or "")[:800])
        log.info("🤖 completion #%d (%dms) → %s%s", step + 1, dt,
                 ("llama: " + ", ".join(tool_names)) if tool_names else "respuesta final",
                 (" | " + res.content[:140]) if res.content else "")
        if not res.tool_calls:
            return res.content or ""
        messages.append(_assistant_msg(res))
        for tc in res.tool_calls:
            executor = executors.get(tc.name)
            if executor is None:
                toolbuffer.record("tool", tc.name, ok=False, args=tc.arguments,
                                  result={"error": "herramienta desconocida"})
                messages.append(_tool_msg(tc.id, {"error": f"herramienta desconocida: {tc.name}"}))
                continue
            model = arg_models.get(tc.name)
            try:
                args = model.model_validate(tc.arguments) if model else tc.arguments
            except Exception as exc:  # → reparación: el LLM verá el error y reintentará
                toolbuffer.record("tool", tc.name, ok=False, args=tc.arguments,
                                  result={"error": "argumentos inválidos", "detail": str(exc)})
                log.info("🔧 %s ✗ argumentos inválidos: %s", tc.name, exc)
                messages.append(_tool_msg(tc.id, {"error": "argumentos inválidos", "detail": str(exc)}))
                continue
            t1 = time.perf_counter()
            try:
                result = await executor(args)
            except Exception as exc:
                ms = int((time.perf_counter() - t1) * 1000)
                log.exception("Fallo ejecutando %s", tc.name)
                toolbuffer.record("tool", tc.name, ok=False, args=tc.arguments,
                                  result={"error": str(exc)}, duration_ms=ms)
                messages.append(_tool_msg(tc.id, {"error": str(exc)}))
                continue
            ms = int((time.perf_counter() - t1) * 1000)
            toolbuffer.record("tool", tc.name, ok=True, args=tc.arguments,
                              result=_truncate(result), duration_ms=ms)
            log.info("🔧 %s (%dms) → %s", tc.name, ms, _summary(result))
            messages.append(_tool_msg(tc.id, result))
    # agotó pasos: si ya produjo un borrador/playlist, devuélvelo con mensaje coherente
    if result_holder and (result_holder.get("draft") or result_holder.get("playlist")):
        return ("Aquí tienes el borrador — afiné hasta donde me dieron los pasos. "
                "Mira las sugerencias si quieres pulirlo un poco más.")
    return "No pude completar la tarea dentro del límite de pasos."
