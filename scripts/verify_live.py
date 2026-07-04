"""Verificación de conectividad con las APIs REALES (usa las claves de .env).
No imprime secretos, solo resultados."""
import asyncio

from app.agent.llm import DeepSeekClient
from app.config import get_settings
from app.enrich.lastfm import LastFmClient
from app.enrich.musicbrainz import MusicBrainzClient


async def main() -> None:
    s = get_settings()

    print("=== Last.fm ===")
    lf = LastFmClient(s.lastfm_api_key)
    try:
        info = await lf.artist_info("Bad Bunny")
        print(f"  ✓ Bad Bunny → {info['listeners']:,} listeners | tags: {info['tags'][:5]}")
    except Exception as e:
        print("  ✗", repr(e)[:200])
    finally:
        await lf.aclose()

    print("=== MusicBrainz ===")
    mb = MusicBrainzClient(s.musicbrainz_user_agent)
    try:
        a = await mb.search_artist("Rosalía")
        mbid = (a or {}).get("mbid") or "?"
        print(f"  ✓ {a['name']} | mbid {mbid[:8]}… | genres {a['genres'][:5]}")
    except Exception as e:
        print("  ✗", repr(e)[:200])
    finally:
        await mb.aclose()

    print(f"=== DeepSeek (modelo '{s.deepseek_model}') ===")
    ds = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
    try:
        res = await ds.chat([{"role": "user", "content": "Responde EXACTAMENTE: VibeSync online"}])
        print(f"  ✓ respuesta: {res.content!r}")
    except Exception as e:
        print("  ✗", repr(e)[:300])
    finally:
        await ds.aclose()


if __name__ == "__main__":
    asyncio.run(main())
