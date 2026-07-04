"""Capa LLM abstraída (OpenAI-compatible). DeepSeek en prod, FakeLLM en tests.

Mantener esta interfaz permite cambiar de proveedor sin tocar el runner ni las tools.
"""
import json
from dataclasses import dataclass, field
from typing import Protocol

import httpx


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(Protocol):
    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult: ...


class DeepSeekClient:
    """DeepSeek V4 Flash vía endpoint OpenAI-compatible (/chat/completions)."""

    def __init__(self, api_key: str, base_url: str, model: str,
                 client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = client or httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def chat(self, messages, tools=None) -> ChatResult:
        payload: dict = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
        r = await self.client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        calls = [
            ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=json.loads(tc["function"].get("arguments") or "{}"),
            )
            for tc in (msg.get("tool_calls") or [])
        ]
        return ChatResult(content=msg.get("content"), tool_calls=calls)


class FakeLLM:
    """Reproduce ChatResult programados. `calls` guarda los mensajes recibidos."""

    def __init__(self, script: list[ChatResult]) -> None:
        self._script = list(script)
        self.calls: list[list[dict]] = []

    async def chat(self, messages, tools=None) -> ChatResult:
        self.calls.append([dict(m) for m in messages])
        return self._script.pop(0)
