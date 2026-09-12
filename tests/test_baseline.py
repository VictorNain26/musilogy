from pathlib import Path

import duckdb
import pytest

from musilogy.build import build, check_invariants
from musilogy.paths import SQL_DIR

# members: 646 620 relations extracted, of which 44 795 are byte-identical
# rows (the dump emits one relation per set of attributes) and 66 more collapse
# once the dates are read as years. No relation is lost to a NULL person: the
# reference dump carries none.
BASELINE = {
    "bands": 682_447,
    "albums": 643_403,
    "genres": 1_348,
    "density": 53_029,
    "members": 601_759,
}
Y0_SOURCE_BREAKDOWN = {"declared": 235_246, "first_album": 145_620, None: 301_581}
Y_END_SOURCE_BREAKDOWN = {"declared": 48_842, "last_album": 251_514, None: 382_091}
PLACEABLE = 380_866
DENSITY_PRESENT = 1_983_329
# The date readings the dump loses, and the album inferences the guards of
# 30_bands_lifespan.sql refuse. Frozen here too: a guard that stops firing is
# as much a regression as a count that moves.
DATE_ANOMALIES = {
    "begin_illegible": 34,
    "end_illegible": 7,
    "begin_future": 15,
    "end_future": 3,
    "begin_below_min_year": 258,
    "end_below_min_year": 4,
    "end_before_begin": 2,
}
NEUTRALISED_INFERENCES = {
    "first_album_after_declared_end": 81,
    "last_album_before_declared_begin": 271,
    "first_album_with_begin_below_min_year": 73,
}
WORK = Path("data/work")


def single_row(con, table):
    result = con.execute(f"SELECT * FROM {table}")
    return dict(zip([c[0] for c in result.description], result.fetchone(), strict=True))


@pytest.mark.slow
def test_reference_dump_matches_the_baseline():
    if not (WORK / "artists.jsonl").exists() or not (WORK / "release_groups.jsonl").exists():
        pytest.skip("extractions missing: run Task 3")
    con = duckdb.connect(":memory:")
    build(con, SQL_DIR, WORK / "artists.jsonl", WORK / "release_groups.jsonl", None)
    assert check_invariants(con, SQL_DIR) == []
    for table, expected in BASELINE.items():
        row = con.execute(f"SELECT count(*) FROM {table}").fetchone()
        assert row is not None
        got = row[0]
        assert got == expected, f"{table}: expected {expected}, got {got}"

    got_y0_source = dict(
        con.execute("SELECT y0_source, count(*) FROM bands GROUP BY y0_source").fetchall()
    )
    assert got_y0_source == Y0_SOURCE_BREAKDOWN

    got_y_end_source = dict(
        con.execute("SELECT y_end_source, count(*) FROM bands GROUP BY y_end_source").fetchall()
    )
    assert got_y_end_source == Y_END_SOURCE_BREAKDOWN

    row = con.execute("SELECT count(*) FROM bands WHERE y0 IS NOT NULL").fetchone()
    assert row is not None
    assert row[0] == PLACEABLE

    # The cell count alone says nothing about what fills the cells: a band
    # gained or lost inside an existing (genre, year) moves present without
    # moving the count.
    row = con.execute("SELECT sum(present) FROM density").fetchone()
    assert row is not None
    assert row[0] == DENSITY_PRESENT

    assert single_row(con, "r2_anomalies") == DATE_ANOMALIES
    assert single_row(con, "neutralised_inferences") == NEUTRALISED_INFERENCES

    row = con.execute(
        "SELECT count(*) FROM bands WHERE y_end IS NOT NULL AND y0 IS NOT NULL AND y_end < y0"
    ).fetchone()
    assert row is not None
    assert row[0] == 0
