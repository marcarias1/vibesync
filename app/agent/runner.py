"""Bucle de tool-calling con validación + reparación de argumentos.

Si el LLM manda argumentos inválidos, se le devuelve el error como resultado de
la herramienta y se le da otra oportunidad (auto-reparación), sin romper la sesión.
"""
import json
import logging
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from app.agent.llm import ChatResult, LLMClient

log = logging.getLogger(__name__)

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
) -> str:
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]
    for _ in range(max_iters):
        res = await llm.chat(messages, tool_schemas)
        if not res.tool_calls:
            return res.content or ""
        messages.append(_assistant_msg(res))
        for tc in res.tool_calls:
            executor = executors.get(tc.name)
            if executor is None:
                messages.append(_tool_msg(tc.id, {"error": f"herramienta desconocida: {tc.name}"}))
                continue
            model = arg_models.get(tc.name)
            try:
                args = model.model_validate(tc.arguments) if model else tc.arguments
            except Exception as exc:  # → reparación: el LLM verá el error y reintentará
                messages.append(_tool_msg(tc.id, {"error": "argumentos inválidos", "detail": str(exc)}))
                continue
            try:
                result = await executor(args)
            except Exception as exc:
                log.exception("Fallo ejecutando %s", tc.name)
                messages.append(_tool_msg(tc.id, {"error": str(exc)}))
                continue
            messages.append(_tool_msg(tc.id, result))
    return "No pude completar la tarea dentro del límite de pasos."
