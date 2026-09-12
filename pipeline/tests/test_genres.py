from pathlib import Path
import duckdb
import pytest
from pipeline.build import build

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")
OH3 = "125948ec-7f91-4d1a-8b83-accbf50fae3d"


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def test_genres_are_sorted_by_votes_then_name(con):
    names = con.execute(
        "SELECT list_transform(genres, g -> g.name) FROM bands WHERE mbid = ?", [OH3]
    ).fetchone()[0]
    assert names[0] == "synth-pop"
    assert names[1:5] == ["crunkcore", "electronic", "electropop", "pop"]


def test_genres_table_counts_bands(con):
    assert con.execute("""
        SELECT g.n_bands = (SELECT count(*) FROM bands b
                            WHERE list_contains(list_transform(b.genres, x -> x.mbid), g.genre_mbid))
        FROM genres g
    """).fetchall() == [(True,)] * con.execute("SELECT count(*) FROM genres").fetchone()[0]


def test_every_band_genre_exists_in_the_genres_table(con):
    assert con.execute("""
        SELECT count(*) FROM (SELECT unnest(genres) AS g FROM bands) t
        WHERE t.g.mbid NOT IN (SELECT genre_mbid FROM genres)
    """).fetchall() == [(0,)]
