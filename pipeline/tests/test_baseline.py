from pathlib import Path
import duckdb
import pytest
from pipeline.build import build, check_invariants

BASELINE = {"bands": 63_487, "albums": 189_477, "genres": 1_236, "density": 51_161}
WORK = Path("data/work")


@pytest.mark.slow
def test_reference_dump_matches_the_baseline():
    if not (WORK / "artists.jsonl").exists() or not (WORK / "release_groups.jsonl").exists():
        pytest.skip("extractions absentes : lancer la Task 3")
    con = duckdb.connect(":memory:")
    build(con, Path("pipeline/sql"), WORK / "artists.jsonl",
          WORK / "release_groups.jsonl", None)
    assert check_invariants(con, Path("pipeline/sql")) == []
    for table, expected in BASELINE.items():
        got = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        assert got == expected, f"{table} : attendu {expected}, obtenu {got}"
