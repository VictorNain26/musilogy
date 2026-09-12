from pathlib import Path
import duckdb
import pytest
from pipeline.build import build, check_invariants

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def test_build_skips_90_files(con):
    with pytest.raises(duckdb.CatalogException):
        con.execute("SELECT * FROM duplicate_band")


def test_fixtures_satisfy_every_invariant(con):
    assert check_invariants(con, SQL) == []


def test_a_broken_invariant_is_reported(con):
    con.execute("INSERT INTO albums VALUES ('inconnu', 'rg', 'T', 1999, false)")
    violations = dict(check_invariants(con, SQL))
    con.execute("DELETE FROM albums WHERE band_mbid = 'inconnu'")
    assert violations.get("album_without_band") == 1


def test_duplicate_band_is_reported(con):
    row = con.execute("SELECT * FROM bands LIMIT 1").fetchone()
    cols = [d[0] for d in con.description]
    placeholders = ", ".join("?" for _ in cols)
    con.execute(f"INSERT INTO bands VALUES ({placeholders})", row)
    violations = dict(check_invariants(con, SQL))
    con.execute(
        f"DELETE FROM bands WHERE mbid = ? AND rowid IN "
        f"(SELECT rowid FROM bands WHERE mbid = ? LIMIT 1)",
        [row[cols.index("mbid")], row[cols.index("mbid")]],
    )
    assert violations.get("duplicate_band") == 1


def test_band_out_of_window_is_reported(con):
    mbid = con.execute("SELECT mbid FROM bands LIMIT 1").fetchone()[0]
    con.execute("UPDATE bands SET y0 = 1700 WHERE mbid = ?", [mbid])
    violations = dict(check_invariants(con, SQL))
    con.execute("UPDATE bands SET y0 = 1850 WHERE mbid = ?", [mbid])
    assert violations.get("band_out_of_window") == 1


def test_end_before_begin_is_reported(con):
    mbid = con.execute("SELECT mbid FROM bands WHERE y0 > 1850 LIMIT 1").fetchone()[0]
    y0 = con.execute("SELECT y0 FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    con.execute("UPDATE bands SET y_end_declared = ? WHERE mbid = ?", [y0 - 1, mbid])
    violations = dict(check_invariants(con, SQL))
    con.execute("UPDATE bands SET y_end_declared = NULL WHERE mbid = ?", [mbid])
    assert violations.get("end_before_begin") == 1


def test_last_album_mismatch_is_reported(con):
    mbid = con.execute(
        "SELECT mbid FROM bands WHERE y_last_album IS NOT NULL LIMIT 1"
    ).fetchone()[0]
    original = con.execute(
        "SELECT y_last_album FROM bands WHERE mbid = ?", [mbid]
    ).fetchone()[0]
    con.execute("UPDATE bands SET y_last_album = ? WHERE mbid = ?", [original - 1, mbid])
    violations = dict(check_invariants(con, SQL))
    con.execute("UPDATE bands SET y_last_album = ? WHERE mbid = ?", [original, mbid])
    assert violations.get("last_album_mismatch") == 1


def test_album_out_of_window_is_reported(con):
    rg_mbid = con.execute("SELECT rg_mbid FROM albums LIMIT 1").fetchone()[0]
    original = con.execute(
        "SELECT y FROM albums WHERE rg_mbid = ?", [rg_mbid]
    ).fetchone()[0]
    con.execute("UPDATE albums SET y = 2026 WHERE rg_mbid = ?", [rg_mbid])
    violations = dict(check_invariants(con, SQL))
    con.execute("UPDATE albums SET y = ? WHERE rg_mbid = ?", [original, rg_mbid])
    assert violations.get("album_out_of_window") == 1


def test_band_without_genre_is_reported(con):
    mbid = con.execute("SELECT mbid FROM bands LIMIT 1").fetchone()[0]
    original = con.execute("SELECT genres FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    con.execute("UPDATE bands SET genres = [] WHERE mbid = ?", [mbid])
    violations = dict(check_invariants(con, SQL))
    con.execute("UPDATE bands SET genres = ? WHERE mbid = ?", [original, mbid])
    assert violations.get("band_without_genre") == 1


def test_band_genres_out_of_order_is_reported(con):
    mbid = con.execute(
        "SELECT mbid FROM bands WHERE len(genres) > 1 LIMIT 1"
    ).fetchone()[0]
    original = con.execute("SELECT genres FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    con.execute(
        "UPDATE bands SET genres = list_reverse(genres) WHERE mbid = ?", [mbid]
    )
    reversed_genres = con.execute(
        "SELECT genres FROM bands WHERE mbid = ?", [mbid]
    ).fetchone()[0]
    violations = dict(check_invariants(con, SQL))
    con.execute("UPDATE bands SET genres = ? WHERE mbid = ?", [original, mbid])
    assume_effective = reversed_genres != original
    assert assume_effective
    assert violations.get("band_genres_out_of_order") == 1


def test_unknown_genre_is_reported(con):
    mbid = con.execute("SELECT mbid FROM bands LIMIT 1").fetchone()[0]
    original = con.execute("SELECT genres FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    con.execute(
        "UPDATE bands SET genres = list_append(genres, "
        "{'mbid': 'inconnu', 'name': 'x', 'votes': 1}) WHERE mbid = ?",
        [mbid],
    )
    violations = dict(check_invariants(con, SQL))
    con.execute("UPDATE bands SET genres = ? WHERE mbid = ?", [original, mbid])
    assert violations.get("unknown_genre") == 1


def test_presence_out_of_range_is_reported(con):
    mbid = con.execute("SELECT mbid FROM presence LIMIT 1").fetchone()[0]
    original = con.execute(
        "SELECT y_presence_end FROM presence WHERE mbid = ?", [mbid]
    ).fetchone()[0]
    con.execute("UPDATE presence SET y_presence_end = 2100 WHERE mbid = ?", [mbid])
    violations = dict(check_invariants(con, SQL))
    con.execute(
        "UPDATE presence SET y_presence_end = ? WHERE mbid = ?", [original, mbid]
    )
    assert violations.get("presence_out_of_range") == 1


def test_density_out_of_range_is_reported(con):
    row = con.execute("SELECT * FROM density LIMIT 1").fetchone()
    cols = [d[0] for d in con.description]
    con.execute(
        f"INSERT INTO density VALUES ({', '.join('?' for _ in cols)})",
        [row[cols.index("genre_mbid")], 2100, row[cols.index("present")]],
    )
    violations = dict(check_invariants(con, SQL))
    con.execute(
        "DELETE FROM density WHERE genre_mbid = ? AND year = 2100",
        [row[cols.index("genre_mbid")]],
    )
    assert violations.get("density_out_of_range") == 1


def test_genre_parent_unknown_genre_is_reported(con):
    con.execute("INSERT INTO genre_parents VALUES ('inconnu', 'inconnu-parent', 'wikidata')")
    violations = dict(check_invariants(con, SQL))
    con.execute("DELETE FROM genre_parents WHERE genre_mbid = 'inconnu'")
    assert violations.get("genre_parent_unknown_genre") == 2


def test_genre_parent_cycle_is_reported(con):
    con.execute("INSERT INTO genres VALUES ('cycle-a', 'A', 0), ('cycle-b', 'B', 0)")
    con.execute(
        "INSERT INTO genre_parents VALUES "
        "('cycle-a', 'cycle-b', 'wikidata'), ('cycle-b', 'cycle-a', 'wikidata')"
    )
    violations = dict(check_invariants(con, SQL))
    con.execute("DELETE FROM genre_parents WHERE genre_mbid IN ('cycle-a', 'cycle-b')")
    con.execute("DELETE FROM genres WHERE genre_mbid IN ('cycle-a', 'cycle-b')")
    assert violations.get("genre_parent_cycle") == 2


def test_density_above_band_count_is_reported(con):
    row = con.execute("SELECT genre_mbid, year, present FROM density LIMIT 1").fetchone()
    genre_mbid, year, original_present = row
    n_bands = con.execute(
        "SELECT n_bands FROM genres WHERE genre_mbid = ?", [genre_mbid]
    ).fetchone()[0]
    con.execute(
        "UPDATE density SET present = ? WHERE genre_mbid = ? AND year = ?",
        [n_bands + 1, genre_mbid, year],
    )
    violations = dict(check_invariants(con, SQL))
    con.execute(
        "UPDATE density SET present = ? WHERE genre_mbid = ? AND year = ?",
        [original_present, genre_mbid, year],
    )
    assert violations.get("density_above_band_count") == 1
