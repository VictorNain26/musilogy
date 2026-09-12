# pipeline/tests/test_corrections.py
from pathlib import Path
import duckdb
from pipeline.build import build

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")
BLACKDEATH = "53fc0417-7585-490c-b2ea-5f9737e14c0f"


def build_with(tmp_path, lines):
    path = tmp_path / "corrections.csv"
    path.write_text(
        "mbid,champ,valeur,justification,source\n" + "".join(lines), encoding="utf-8"
    )
    con = duckdb.connect(":memory:")
    build(con, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", path)
    return con


def test_empty_corrections_leave_the_end_neutralised(tmp_path):
    con = build_with(tmp_path, [])
    assert con.execute(
        "SELECT y_end_declared FROM bands WHERE mbid = ?", [BLACKDEATH]
    ).fetchall() == [(None,)]


def test_a_correction_repairs_the_end(tmp_path):
    con = build_with(
        tmp_path,
        [f'{BLACKDEATH},end,2007,"fin réelle","https://example.invalid/source"\n'],
    )
    assert con.execute(
        "SELECT y_end_declared FROM bands WHERE mbid = ?", [BLACKDEATH]
    ).fetchall() == [(2007,)]


def test_a_correction_touches_no_other_band(tmp_path):
    before = build_with(tmp_path, []).execute(
        "SELECT count(*) FROM bands"
    ).fetchone()[0]
    after = build_with(
        tmp_path,
        [f'{BLACKDEATH},end,2007,"fin réelle","https://example.invalid/source"\n'],
    ).execute("SELECT count(*) FROM bands").fetchone()[0]
    assert before == after


def test_a_correction_does_not_change_other_bands_dates(tmp_path):
    other = "9a58fda3-f4ed-4080-a3a5-f457aac9fcdd"
    before = build_with(tmp_path, []).execute(
        "SELECT y0, y_end_declared FROM bands WHERE mbid = ?", [other]
    ).fetchall()
    after = build_with(
        tmp_path,
        [f'{BLACKDEATH},end,2007,"fin réelle","https://example.invalid/source"\n'],
    ).execute("SELECT y0, y_end_declared FROM bands WHERE mbid = ?", [other]).fetchall()
    assert before == after


def test_genre_counts_stay_consistent_after_a_correction(tmp_path):
    con = build_with(
        tmp_path,
        [f'{BLACKDEATH},end,2007,"fin réelle","https://example.invalid/source"\n'],
    )
    assert con.execute("""
        SELECT count(*) FROM genres g WHERE g.n_bands <> (
          SELECT count(*) FROM bands b
          WHERE list_contains(list_transform(b.genres, x -> x.mbid), g.genre_mbid))
    """).fetchall() == [(0,)]


def test_an_invalid_correction_is_neutralised_by_r2(tmp_path):
    con = build_with(
        tmp_path,
        [f'{BLACKDEATH},end,1500,"correction invalide (fin avant début)","https://example.invalid/source"\n'],
    )
    assert con.execute(
        "SELECT y_end_declared FROM bands WHERE mbid = ?", [BLACKDEATH]
    ).fetchall() == [(None,)]


def test_corrections_file_stays_small():
    path = Path("pipeline/corrections.csv")
    assert len(path.read_text(encoding="utf-8").splitlines()) - 1 <= 50
