from datetime import datetime, timezone

from app.db.models import PlaybackEvent
from app.ingest.importer import filter_entries, parse_entries, to_playback_docs


def _entry(ms, uri="spotify:track:a", reason_end="trackdone", ts="2025-01-01T10:00:00Z"):
    return {
        "ts": ts, "ms_played": ms, "spotify_track_uri": uri, "reason_end": reason_end,
        "master_metadata_track_name": "T", "master_metadata_album_artist_name": "A",
    }


def test_filter_quality():
    raw = [
        _entry(40000),                               # ok
        _entry(1000),                                # < 30s  -> fuera
        _entry(40000, uri=None),                     # sin uri -> fuera
        _entry(40000, reason_end="fwdbtn"),          # skip    -> fuera
    ]
    kept = filter_entries(parse_entries(raw))
    assert len(kept) == 1


def test_deterministic_id():
    ts = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    a = PlaybackEvent.make_id("u1", "spotify:track:x", ts)
    b = PlaybackEvent.make_id("u1", "spotify:track:x", ts)
    assert a == b
    assert PlaybackEvent.make_id("u2", "spotify:track:x", ts) != a


def test_to_docs_uses_alias():
    docs = to_playback_docs("u1", parse_entries([_entry(40000)]))
    assert docs[0]["_id"].startswith("u1:spotify:track:a:")
    assert docs[0]["user_id"] == "u1"
