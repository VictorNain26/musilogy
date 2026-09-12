import json

from conftest import FIX


def test_every_witness_is_present():
    from musilogy.cli import WITNESSES  # noqa: PLC0415

    with (FIX / "artists.jsonl").open(encoding="utf-8") as fh:
        ids = {json.loads(line)["mbid"] for line in fh}
    assert set(WITNESSES) <= ids


def test_beatles_genres_carry_mbid_and_votes():
    with (FIX / "artists.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if rec["mbid"] == "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d":
                assert rec["genres"], "genres must be preserved"
                assert all(g["mbid"] and "votes" in g for g in rec["genres"])
                return
    raise AssertionError("The Beatles missing from fixtures")


def test_release_groups_file_is_well_formed_and_complete():
    with (FIX / "release_groups.jsonl").open(encoding="utf-8") as fh:
        lines = fh.readlines()
    records = [json.loads(line) for line in lines]
    # Number frozen at extraction time: any truncation or dropped line changes it.
    assert len(records) == 3628


def test_every_release_group_credits_a_witness():
    from musilogy.cli import WITNESSES  # noqa: PLC0415

    wanted = set(WITNESSES)
    with (FIX / "release_groups.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            assert wanted & set(rec["artists"]), rec["mbid"]
