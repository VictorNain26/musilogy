from pathlib import Path
import duckdb
import pytest
from pipeline.build import build

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")
BEATLES = "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d"
FLEETWOOD = "bd13909f-1c29-4c27-a874-d4aaf27c5b1a"
DEMENTED = "8a1f012c-acc1-4dda-878f-43ac02f2366f"
CARDIACS = "f7338f2a-136b-4d5e-b099-5504cf997f58"
MAROON = "0ab49580-c84f-44d4-875f-d83760ea2cfe"


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def test_beatles_keep_22_albums_between_1963_and_1970(con):
    assert con.execute(
        "SELECT count(*), min(y), max(y) FROM albums WHERE band_mbid = ?", [BEATLES]
    ).fetchall() == [(22, 1963, 1970)]


def test_soundtracks_are_kept(con):
    n = con.execute(
        "SELECT count(*) FROM albums WHERE band_mbid = ? AND soundtrack", [BEATLES]
    ).fetchone()[0]
    assert n > 0


def test_multi_artist_album_is_dropped(con):
    assert con.execute(
        "SELECT count(*) FROM albums WHERE rg_mbid IN "
        "(SELECT mbid FROM raw_release_groups WHERE title = 'The Biggest Thing Since Colossus')"
    ).fetchall() == [(0,)]


def test_same_artist_credited_twice_is_kept(con):
    assert con.execute(
        "SELECT count(*) FROM albums WHERE band_mbid = ? AND title = ?",
        [DEMENTED, "The Day the Earth Spat Blood"],
    ).fetchall() == [(1,)]


def test_posthumous_album_inside_the_margin_is_kept(con):
    assert con.execute(
        "SELECT max(y) FROM albums WHERE band_mbid = ?", [CARDIACS]
    ).fetchall() == [(2025,)]


def test_album_before_formation_is_kept_within_five_years(con):
    assert con.execute(
        "SELECT min(y) FROM albums WHERE band_mbid = ?", [MAROON]
    ).fetchall() == [(1997,)]
