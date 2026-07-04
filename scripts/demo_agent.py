"""Demo offline del agente DJ: ejecuta el bucle de tool-calling completo con un
FakeLLM (sin ninguna API key ni login). Prueba end-to-end runner + tools + executors.

Uso:  PYTHONPATH=. .venv/bin/python scripts/demo_agent.py
"""
import asyncio

from app.agent.llm import ChatResult, FakeLLM, ToolCall
from app.agent.runner import run_agent
from app.agent.tools import ARG_MODELS


async def main() -> None:
    # Guion del "LLM": pide contexto temporal → busca por vibe → crea la playlist → responde.
    script = [
        ChatResult(tool_calls=[ToolCall("t1", "get_temporal_context", {})]),
        ChatResult(tool_calls=[ToolCall("t2", "semantic_track_search",
                                        {"vibe_query": "trap latino oscuro para la noche", "limit": 3})]),
        ChatResult(tool_calls=[ToolCall("t3", "spotify_playlist_controller",
                                        {"playlist_name": "Noche VibeSync",
                                         "track_uris": ["spotify:track:a", "spotify:track:b", "spotify:track:c"],
                                         "mode": "create"})]),
        ChatResult(content="🎧 Lista 'Noche VibeSync' creada con 3 temas underground que encajan con tu vibe nocturno."),
    ]
    llm = FakeLLM(script)

    # Executors fake (sin BD ni Spotify reales) que registran e imprimen cada paso.
    async def temporal(_):
        r = {"hour": 23, "weekday": "Friday"}
        print("  · get_temporal_context ->", r)
        return r

    async def semantic(args):
        r = {"count": 3, "tracks": [{"uri": f"spotify:track:{c}", "name": n}
                                    for c, n in zip("abc", ["Underground I", "Neoperreo II", "Dark Trap III"])]}
        print(f"  · semantic_track_search('{args.vibe_query}') ->", r["count"], "tracks")
        return r

    async def playlist(args):
        r = {"playlist_id": "pl_demo_123", "tracks": len(args.track_uris)}
        print(f"  · spotify_playlist_controller('{args.playlist_name}', mode={args.mode}) ->", r)
        return r

    executors = {
        "get_temporal_context": temporal,
        "semantic_track_search": semantic,
        "spotify_playlist_controller": playlist,
    }

    print("Usuario: 'Ponme algo underground para esta noche y guárdalo en una playlist'\n")
    print("El agente ejecuta herramientas:")
    answer = await run_agent(llm, executors, ARG_MODELS, "algo underground para la noche, guárdalo")
    print("\nAgente:", answer)
    print(f"\n[LLM invocado {len(llm.calls)} veces | bucle de tool-calling OK]")


if __name__ == "__main__":
    asyncio.run(main())
