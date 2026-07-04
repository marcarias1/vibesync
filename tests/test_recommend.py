from app.agent.recommend import filter_underground, vector_search_pipeline


def test_pipeline_shape():
    p = vector_search_pipeline([0.1, 0.2, 0.3], limit=5, num_candidates=100)
    vs = p[0]["$vectorSearch"]
    assert vs["index"] == "vec_tracks"
    assert vs["path"] == "embedding"
    assert vs["limit"] == 5 and vs["numCandidates"] == 100
    assert p[1]["$project"]["score"] == {"$meta": "vectorSearchScore"}


def test_filter_underground_combines_window_and_tags():
    cands = [
        {"name": "underground", "commerciality_score": 30, "tags": ["trap", "latino"]},
        {"name": "mainstream", "commerciality_score": 85, "tags": ["trap", "latino"]},
        {"name": "off-genre", "commerciality_score": 40, "tags": ["jazz"]},
    ]
    out = filter_underground(50, cands, source_tags=["trap", "latino"], min_jaccard=0.4)
    assert [c["name"] for c in out] == ["underground"]
