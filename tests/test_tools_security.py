import pytest
from pydantic import ValidationError

from app.agent.tools import PlaylistControllerArgs, SearchTracksArgs, build_match


def test_rejects_nosql_operator_injection():
    with pytest.raises(ValidationError):
        SearchTracksArgs(artist_name="$where")
    with pytest.raises(ValidationError):
        SearchTracksArgs(genre="{'$ne': null}")   # llaves fuera del charset seguro


def test_rejects_bad_bounds():
    with pytest.raises(ValidationError):
        SearchTracksArgs(min_plays=-1)
    with pytest.raises(ValidationError):
        SearchTracksArgs(limit=999)


def test_build_match_is_safe():
    m = build_match(SearchTracksArgs(artist_name="AC/DC", tag="Rock", genre="Metal"))
    assert m["artist_name"] == {"$regex": "AC/DC", "$options": "i"}   # regex escapado
    assert set(m["tags"]["$in"]) == {"rock", "metal"}                 # normalizado


def test_playlist_uris_validated():
    with pytest.raises(ValidationError):
        PlaylistControllerArgs(playlist_name="x", track_uris=["http://evil"])
    ok = PlaylistControllerArgs(playlist_name="x", track_uris=["spotify:track:abc"])
    assert ok.mode == "create"


def test_build_match_min_plays():
    assert build_match(SearchTracksArgs(min_plays=5))["play_count"] == {"$gte": 5}
    assert "play_count" not in build_match(SearchTracksArgs())  # 0 -> no filtro
