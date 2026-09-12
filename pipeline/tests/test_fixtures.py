import json
from pathlib import Path

FIX = Path("pipeline/tests/fixtures")


def test_every_witness_is_present():
    from scripts.make_fixtures import WITNESSES  # noqa: PLC0415
    ids = {json.loads(l)["mbid"] for l in open(FIX / "artists.jsonl", encoding="utf-8")}
    assert set(WITNESSES) <= ids


def test_beatles_genres_carry_mbid_and_votes():
    for line in open(FIX / "artists.jsonl", encoding="utf-8"):
        rec = json.loads(line)
        if rec["mbid"] == "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d":
            assert rec["genres"], "les genres doivent être conservés"
            assert all(g["mbid"] and "votes" in g for g in rec["genres"])
            return
    raise AssertionError("The Beatles absent des fixtures")


def test_release_groups_file_is_well_formed_and_complete():
    lines = open(FIX / "release_groups.jsonl", encoding="utf-8").readlines()
    records = [json.loads(line) for line in lines]
    # Nombre figé au moment de l'extraction : toute troncature ou ligne perdue le change.
    assert len(records) == 3613


def test_every_release_group_credits_a_witness():
    from scripts.make_fixtures import WITNESSES  # noqa: PLC0415
    wanted = set(WITNESSES)
    for line in open(FIX / "release_groups.jsonl", encoding="utf-8"):
        rec = json.loads(line)
        assert wanted & set(rec["artists"]), rec["mbid"]
