"""Verificación END-TO-END sin claves: embeddings BGE-M3 REALES + $vectorSearch REAL.

Descarga BGE-M3, indexa 3 tracks con descripciones distintas en Atlas-local y
comprueba que una query semántica en español rankea primero el track correcto
(match semántico real, no fuerza bruta).

Uso:  .venv/bin/python scripts/verify_semantic.py
Requiere el contenedor atlas-local (docker compose up) en el puerto 27020.
"""
import asyncio
import sys

from pymongo import AsyncMongoClient
from pymongo.operations import SearchIndexModel

from app.enrich.embeddings import BGEEmbedder

URI = "mongodb://127.0.0.1:27020/?directConnection=true"
TRACKS = [
    ("spotify:track:dark", "Perreo oscuro trap latino de noche, underground y denso"),
    ("spotify:track:happy", "Reggaeton pop veraniego, alegre y muy comercial de radio"),
    ("spotify:track:acoustic", "Balada acústica triste con guitarra, melancólica y lenta"),
]
QUERY = "algo oscuro de trap para programar de noche"


async def _search_indexes(coll):
    cur = await coll.list_search_indexes()
    return [ix async for ix in cur]


async def main() -> None:
    print("· Cargando BGE-M3 real (descarga ~2GB la 1ª vez)…", flush=True)
    emb = BGEEmbedder("BAAI/bge-m3", 1024)
    emb.encode("warmup")

    client = AsyncMongoClient(URI)
    coll = client["vibesync_verify"]["tracks"]
    await coll.delete_many({})

    # 1) insertar ANTES de crear el índice: create_search_index exige que la colección exista
    for uri, text in TRACKS:
        await coll.update_one({"_id": uri},
                              {"$set": {"uri": uri, "name": text, "embedding": emb.encode(text)}},
                              upsert=True)
    print(f"· {len(TRACKS)} tracks indexados con embeddings BGE-M3 reales.", flush=True)

    # 2) índice vectorial
    if "vec_tracks" not in {ix["name"] for ix in await _search_indexes(coll)}:
        await coll.create_search_index(SearchIndexModel(
            name="vec_tracks", type="vectorSearch",
            definition={"fields": [{"type": "vector", "path": "embedding",
                                    "numDimensions": 1024, "similarity": "cosine"}]}))
        print("· Índice vectorial creado; esperando a que esté queryable…", flush=True)

    for _ in range(180):
        ix = [i for i in await _search_indexes(coll) if i["name"] == "vec_tracks"]
        if ix and ix[0].get("queryable"):
            break
        await asyncio.sleep(1)
    else:
        print("✗ timeout esperando el índice vectorial"); sys.exit(1)
    print("· Índice READY.", flush=True)

    # 3) query semántica
    qv = emb.encode(QUERY)
    pipeline = [
        {"$vectorSearch": {"index": "vec_tracks", "path": "embedding",
                           "queryVector": qv, "numCandidates": 50, "limit": 3}},
        {"$project": {"_id": 1, "name": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]
    results = []
    for _ in range(60):  # mongot sincroniza de forma eventual
        results = await (await coll.aggregate(pipeline)).to_list(None)
        if len(results) == len(TRACKS):
            break
        await asyncio.sleep(1)

    print(f"\nQuery: '{QUERY}'\nRanking por similitud coseno (BGE-M3 + $vectorSearch):")
    for r in results:
        print(f"  {r['score']:.4f}  {r['_id']:<24} {r['name']}")

    top = results[0]["_id"] if results else None
    assert top == "spotify:track:dark", f"esperaba 'dark' primero, salió {top!r}"
    print("\n✅ El track oscuro de trap rankea PRIMERO ante una query nocturna: "
          "embeddings BGE-M3 reales + vector search real funcionan de punta a punta.")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
