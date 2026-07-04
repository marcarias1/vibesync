"""Re-enriquece TODOS los artistas con bio + tags limpios y re-embebe (BGE-M3 real).
Muestra los cosenos antes/después para ver si los embeddings se separan mejor.

Uso:  .venv/bin/python scripts/reembed_artists.py
"""
import asyncio
import math

from pymongo import AsyncMongoClient

from app.config import get_settings
from app.enrich.embeddings import get_embedder
from app.enrich.lastfm import LastFmClient
from app.enrich.service import enrich_artist

PAIRS = [("Bad Bunny", "Mora"), ("Bad Bunny", "Feid"),
         ("Bad Bunny", "Saramalacara"), ("Feid", "Saramalacara")]


async def _cos(db, n1, n2):
    a = await db["artists"].find_one({"name": n1})
    b = await db["artists"].find_one({"name": n2})
    if not (a and b and a.get("embedding") and b.get("embedding")):
        return None
    x, y = a["embedding"], b["embedding"]
    s = sum(p * q for p, q in zip(x, y))
    na = math.sqrt(sum(p * p for p in x))
    nb = math.sqrt(sum(q * q for q in y))
    return s / (na * nb) if na and nb else 0.0


async def _show(db, label):
    print(label)
    for n1, n2 in PAIRS:
        c = await _cos(db, n1, n2)
        print(f"  {n1:<12} vs {n2:<14} = {c:.3f}" if c is not None else f"  {n1} vs {n2} = n/a")


async def main():
    s = get_settings()
    client = AsyncMongoClient(s.mongo_uri)
    db = client[s.mongo_db]
    emb = get_embedder()
    lf = LastFmClient(s.lastfm_api_key)

    await _show(db, "ANTES (solo tags):")
    names = [a["name"] async for a in db["artists"].find({}, {"name": 1})]
    print(f"\nRe-enriqueciendo {len(names)} artistas (bio + tags limpios + re-embed)…", flush=True)
    ok = 0
    for i, name in enumerate(names):
        try:
            await enrich_artist(db, name, lastfm=lf, embedder=emb)
            ok += 1
        except Exception:
            pass
        if (i + 1) % 40 == 0:
            print(f"  {i + 1}/{len(names)}", flush=True)
    await lf.aclose()
    print(f"Re-enriquecidos {ok}/{len(names)}.\n")

    await _show(db, "DESPUÉS (bio + tags limpios):")
    bb = await db["artists"].find_one({"name": "Feid"}, {"tags": 1, "bio": 1})
    if bb:
        print("\nEjemplo Feid → tags:", bb.get("tags"))
        print("Ejemplo Feid → bio:", (bb.get("bio") or "")[:180])
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
