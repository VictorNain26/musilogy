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


def rows(con, q):
    return con.execute(q).fetchall()


def test_orchestra_is_excluded(con):
    assert rows(con, "SELECT count(*) FROM bands WHERE mbid = 'd770374d-05e9-4ed3-a068-3fbd4e6e4dd6'") == [(0,)]


def test_unreadable_begin_is_excluded(con):
    assert rows(con, "SELECT count(*) FROM bands WHERE mbid = '1434b0d0-d647-421e-b345-1b9847045a52'") == [(0,)]


def test_future_begin_is_excluded(con):
    assert rows(con, "SELECT count(*) FROM bands WHERE mbid = 'd25be955-6fed-4303-bffb-8c440c191edb'") == [(0,)]


def test_homonyms_without_date_or_genre_are_excluded(con):
    assert rows(con, """
        SELECT count(*) FROM bands
        WHERE mbid IN ('9d953ee6-4ea6-4b0e-aea6-7268d380bef1',
                       '8d3431db-bc83-4dc2-93b8-0e46e31d09f7',
                       '6959c3d5-3e7f-41bb-aba3-50e38225d23d')
    """) == [(0,)]


def test_end_before_begin_is_neutralised_and_band_kept(con):
    assert rows(con, """
        SELECT y0, y_end_declared FROM bands
        WHERE mbid = '53fc0417-7585-490c-b2ea-5f9737e14c0f'
    """) == [(1998, None)]


def test_unreadable_end_is_absent_but_band_kept(con):
    assert rows(con, """
        SELECT y0, y_end_declared, ended FROM bands
        WHERE mbid = '6dfa03fb-8b02-4055-b7cc-e48f426b13f8'
    """) == [(1999, None, True)]


def test_month_precision_is_reduced_to_the_year(con):
    assert rows(con, """
        SELECT y0, y_end_declared FROM bands
        WHERE mbid = '9a58fda3-f4ed-4080-a3a5-f457aac9fcdd'
    """) == [(1978, 1980)]


def test_group_without_genre_is_excluded(con):
    # The Belle Stars: Group, begin=1980, end=1986, aucun genre — ne peut
    # être écarté que par la condition de genre de R1.
    assert rows(con, "SELECT count(*) FROM bands WHERE mbid = '62f7a211-0056-45fe-934a-37a388a7356f'") == [(0,)]


def test_begin_before_lower_bound_is_excluded(con):
    # Handel and Haydn Society: Group, begin=1815, avec genre — ne peut être
    # écarté que par la borne basse 1850 de R1.
    assert rows(con, "SELECT count(*) FROM bands WHERE mbid = '35ddcb29-4c16-4af6-b6f8-32143ee24a6c'") == [(0,)]


def test_future_end_is_absent_in_dated(con):
    # Thunder Jolt: end=2027-01-05, postérieur à dump_year=2026. Aucun
    # témoin réel de fin future ne porte de genre (donc jamais dans `bands`,
    # écarté avant par R1) : on éprouve R2 sur la table intermédiaire `dated`.
    assert rows(con, """
        SELECT y_end_declared FROM dated
        WHERE mbid = 'd36b0fad-abd7-44e4-88fa-f638bbf8c9a6'
    """) == [(None,)]
