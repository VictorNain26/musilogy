from pipeline.extract import reduce_artist, reduce_release_group

GROUP = {
    "id": "a9424175-8b06-44ad-a1f4-319e92a50879",
    "name": "Disincarnate",
    "type": "Group",
    "country": "US",
    "life-span": {"begin": "1992", "end": None, "ended": False},
    "area": {"name": "United States"},
    "begin-area": {"name": "Tampa"},
    "genres": [{"id": "eacfa027-2fad-413f-a2f1-80fa43674f0b",
                "name": "death metal", "count": 1}],
    "relations": [
        {"type": "member of band", "begin": "1991", "end": "1991",
         "artist": {"id": "5b640e8d-bcb8-45be-a32e-8f4325c8d6c9",
                    "name": "Alex Marquez"}},
        {"type": "discogs", "url": {"resource": "https://example.invalid"}},
    ],
}


def test_reduce_artist_keeps_genre_mbid_and_votes():
    out = reduce_artist(GROUP)
    assert out["mbid"] == GROUP["id"]
    assert out["begin"] == "1992"
    assert out["ended"] is False
    assert out["begin_area"] == "Tampa"
    assert out["genres"] == [
        {"mbid": "eacfa027-2fad-413f-a2f1-80fa43674f0b",
         "name": "death metal", "votes": 1}
    ]


def test_reduce_artist_keeps_only_member_of_band_relations():
    out = reduce_artist(GROUP)
    assert out["members"] == [
        {"mbid": "5b640e8d-bcb8-45be-a32e-8f4325c8d6c9",
         "begin": "1991", "end": "1991"}
    ]


def test_reduce_artist_drops_persons():
    assert reduce_artist({"id": "x", "name": "y", "type": "Person"}) is None


def test_reduce_release_group_keeps_duplicate_credits():
    rec = {
        "id": "rg", "title": "T", "first-release-date": "1989",
        "primary-type": "Album", "secondary-types": [],
        "artist-credit": [{"artist": {"id": "a"}}, {"artist": {"id": "a"}}],
    }
    assert reduce_release_group(rec)["artists"] == ["a", "a"]


def test_reduce_release_group_drops_singles():
    assert reduce_release_group({"id": "r", "primary-type": "Single"}) is None
