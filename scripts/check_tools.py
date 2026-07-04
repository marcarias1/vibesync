"""Comprueba que el agente usa BIEN las tools: corre el flujo de borrador con
DeepSeek real y clientes reales, imprimiendo cada tool que llama y su resultado."""
import asyncio

from pymongo import AsyncMongoClient

from app.agent.executors import build_executors
from app.agent.llm import DeepSeekClient
from app.agent.runner import run_agent
from app.agent.tools import ARG_MODELS, TOOL_SCHEMAS
from app.config import get_settings
from app.drafts import DRAFT_SYSTEM
from app.enrich.embeddings import get_embedder
from app.enrich.lastfm import LastFmClient
from app.spotify.playlists import SpotifyPlaylistController
from app.spotify.session import current_user, get_access_token


def _wrap(executors):
    wrapped = {}
    for name, fn in executors.items():
        async def w(args, _fn=fn, _n=name):
            shown = args.model_dump() if hasattr(args, "model_dump") else args
            s = str(shown)
            print(f"  🔧 {_n}  {s[:120]}", flush=True)
            r = await _fn(args)
            print(f"      → {str(r)[:140]}", flush=True)
            return r
        wrapped[name] = w
    return wrapped


async def main():
    s = get_settings()
    c = AsyncMongoClient(s.mongo_uri)
    db = c[s.mongo_db]
    user = await current_user(db)
    uid = user["_id"]
    access = await get_access_token(db, uid)
    llm = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
    lastfm = LastFmClient(s.lastfm_api_key)
    spotify = SpotifyPlaylistController(access, db=db) if access else None
    holder = {}
    ex = _wrap(build_executors(db, get_embedder(), uid, lastfm=lastfm, spotify=spotify, result_holder=holder))

    print("PROMPT: borrador estilo Bb trickz underground para la noche\n")
    print("Secuencia de tools que llama el agente:")
    ans = await run_agent(llm, ex, ARG_MODELS,
                          "Borrador estilo Bb trickz, underground, para la noche.",
                          tool_schemas=TOOL_SCHEMAS, max_iters=10, system=DRAFT_SYSTEM)
    print("\nRESPUESTA (recorte):", (ans or "")[:200])
    print("¿Escribió draft en el holder?:", "SÍ ✓" if holder.get("draft") else "NO")
    await llm.aclose(); await lastfm.aclose()
    if spotify: await spotify.aclose()
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())
