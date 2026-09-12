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


def test_parents_reference_known_genres(con):
    assert con.execute("""
        SELECT count(*) FROM genre_parents
        WHERE genre_mbid NOT IN (SELECT genre_mbid FROM genres)
           OR parent_mbid NOT IN (SELECT genre_mbid FROM genres)
    """).fetchall() == [(0,)]


def test_no_genre_is_its_own_parent(con):
    assert con.execute(
        "SELECT count(*) FROM genre_parents WHERE genre_mbid = parent_mbid"
    ).fetchall() == [(0,)]


def test_source_is_recorded(con):
    sources = {r[0] for r in con.execute("SELECT DISTINCT source FROM genre_parents").fetchall()}
    assert sources <= {"wikidata", "musicbrainz"}
    assert sources, "genre_parents must not be empty on the fixtures"


def test_relation_is_multivalued(con):
    row = con.execute("""
        SELECT genre_mbid, count(*) AS n FROM genre_parents
        GROUP BY genre_mbid ORDER BY n DESC LIMIT 1
    """).fetchone()
    assert row is not None
    assert row[1] > 1, "at least one genre must have several parents on the fixtures"


def test_self_reference_is_excluded_by_the_production_sql(tmp_path):
    # The real archive contains no self-reference (0 out of 2515 lines,
    # verified): this test cannot rely on it to exercise the
    # `w.mbid <> w.parentMbid` clause. It replays the real production SQL
    # (same file, archive path substituted) against a synthetic archive
    # that does contain a self-reference.
    real_path = "pipeline/reference/20260912-wikidata-genre-parents.csv"
    sql_text = (SQL / "60_genre_parents.sql").read_text(encoding="utf-8")
    assert real_path in sql_text, "archive path not found in the production SQL"

    synthetic = tmp_path / "synthetic.csv"
    synthetic.write_text(
        "mbid,nom,parentMbid,parentNom\n"
        "g1,Alpha,g1,Alpha\n"
        "g1,Alpha,g2,Beta\n",
        encoding="utf-8",
    )
    c = duckdb.connect(":memory:")
    c.execute("CREATE TABLE genres AS SELECT 'g1' AS genre_mbid UNION ALL SELECT 'g2'")
    c.execute(sql_text.replace(real_path, synthetic.as_posix()))

    assert c.execute("SELECT genre_mbid, parent_mbid FROM genre_parents").fetchall() == [
        ("g1", "g2")
    ]


def test_genre_parents_csv_resolves_independently_of_cwd(tmp_path, monkeypatch):
    # GENRE_PARENTS_CSV resolves from build.py's __file__, not from the
    # process's cwd: run from another directory, the archive is still found
    # and genre_parents is not silently published empty.
    sql_dir = SQL.resolve()
    artists = (FIX / "artists.jsonl").resolve()
    rgs = (FIX / "release_groups.jsonl").resolve()
    monkeypatch.chdir(tmp_path)
    c = duckdb.connect(":memory:")
    build(c, sql_dir, artists, rgs, None)
    assert c.execute("SELECT count(*) FROM genre_parents").fetchone()[0] > 0


def test_build_creates_empty_table_when_archive_is_missing(monkeypatch, tmp_path, caplog):
    import logging

    import pipeline.build as build_mod

    monkeypatch.setattr(build_mod, "GENRE_PARENTS_CSV", tmp_path / "absent.csv")
    c = duckdb.connect(":memory:")
    with caplog.at_level(logging.WARNING, logger="pipeline.build"):
        build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    assert c.execute("SELECT count(*) FROM genre_parents").fetchall() == [(0,)]
    assert any("genre_parents" in r.message for r in caplog.records), (
        "the empty-table fallback must log a warning"
    )
