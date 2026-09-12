from pathlib import Path
import duckdb
import pytest
from pipeline.build import build

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def end_of(con, mbid):
    return con.execute(
        "SELECT y_presence_end FROM presence WHERE mbid = ?", [mbid]
    ).fetchone()[0]


def test_declared_end_wins_over_a_later_album(con):
    # Cardiacs : fin déclarée 2020, album retenu en 2025.
    assert end_of(con, "f7338f2a-136b-4d5e-b099-5504cf997f58") == 2020


def test_active_band_is_not_stopped_at_its_last_album(con):
    # U2 : aucune fin déclarée, dernier album 2025.
    assert end_of(con, "a3cb23fc-acd3-4ce0-8f36-1e5aa6a18432") == 2025


def test_band_without_album_is_present_only_at_formation(con):
    # ROD : formé en 1996, aucun album retenu.
    assert end_of(con, "3cb86073-22d7-43d5-8f22-422b1e54988e") == 1996


def test_albums_before_formation_do_not_move_the_floor(con):
    # Polska Radio One : formé 2015, albums 2013 et 2014.
    assert end_of(con, "703c4c92-43f7-4268-9f85-0ca6f0cd1a22") == 2015


def test_no_band_is_present_after_its_declared_end(con):
    assert con.execute("""
        SELECT count(*) FROM presence p JOIN bands b USING (mbid)
        WHERE b.y_end_declared IS NOT NULL AND p.y_presence_end > b.y_end_declared
    """).fetchall() == [(0,)]


def test_presence_end_is_published_on_bands(con):
    assert con.execute("""
        SELECT count(*) FROM bands b JOIN presence p USING (mbid)
        WHERE b.y_presence_end IS DISTINCT FROM p.y_presence_end
    """).fetchall() == [(0,)]
