from contextlib import contextmanager

import duckdb
import pytest
from conftest import FIX, SQL

from musilogy.build import build, check_invariants


@contextmanager
def restored(con, *undo):
    """Undo the mutation whatever happens. `con` is module-scoped: without a
    finally, a failing assertion would leave it mutated for every test after
    this one, and the failure would spread instead of staying local."""
    try:
        yield
    finally:
        for sql, params in undo:
            con.execute(sql, params)


def test_build_skips_90_files():
    # Dedicated connection, never passed to check_invariants: on `con`
    # (module-scoped, shared by every test in this file), a previous run of
    # 90_invariants.sql would already have created duplicate_band, and this
    # test would only depend on its rank within the file.
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    with pytest.raises(duckdb.CatalogException):
        c.execute("SELECT * FROM duplicate_band")


def test_fixtures_satisfy_every_invariant(con):
    assert check_invariants(con, SQL) == []


def test_a_broken_invariant_is_reported(con):
    with restored(con, ("DELETE FROM albums WHERE band_mbid = 'inconnu'", [])):
        con.execute("INSERT INTO albums VALUES ('inconnu', 'rg', 'T', 1999, false)")
        violations = dict(check_invariants(con, SQL))
    assert violations.get("album_without_band") == 1


def test_album_without_band_survives_a_null_mbid_in_bands(con):
    # NOT IN used to go silent here: a single NULL mbid in the `bands`
    # subquery makes `x NOT IN (subquery)` never true, whatever x is, so a
    # real violation would go unreported. NOT EXISTS is NULL-safe.
    row = con.execute("SELECT * FROM bands LIMIT 1").fetchone()
    cols = [d[0] for d in con.description]
    values = list(row)
    values[cols.index("mbid")] = None
    placeholders = ", ".join("?" for _ in cols)
    with restored(
        con,
        ("DELETE FROM albums WHERE band_mbid = 'inconnu-null-poison'", []),
        ("DELETE FROM bands WHERE mbid IS NULL", []),
    ):
        con.execute(
            "INSERT INTO albums VALUES ('inconnu-null-poison', 'rg-null-poison', 'T', 1999, false)"
        )
        con.execute(f"INSERT INTO bands VALUES ({placeholders})", values)
        violations = dict(check_invariants(con, SQL))
    assert violations.get("album_without_band") == 1


def test_duplicate_band_is_reported(con):
    row = con.execute("SELECT * FROM bands LIMIT 1").fetchone()
    cols = [d[0] for d in con.description]
    placeholders = ", ".join("?" for _ in cols)
    mbid = row[cols.index("mbid")]
    with restored(
        con,
        (
            "DELETE FROM bands WHERE mbid = ? AND rowid IN "
            "(SELECT rowid FROM bands WHERE mbid = ? LIMIT 1)",
            [mbid, mbid],
        ),
    ):
        con.execute(f"INSERT INTO bands VALUES ({placeholders})", row)
        violations = dict(check_invariants(con, SQL))
    assert violations.get("duplicate_band") == 1


def test_duplicate_band_catches_null_mbid(con):
    row = con.execute("SELECT * FROM bands LIMIT 1").fetchone()
    cols = [d[0] for d in con.description]
    values = list(row)
    values[cols.index("mbid")] = None
    placeholders = ", ".join("?" for _ in cols)
    with restored(con, ("DELETE FROM bands WHERE mbid IS NULL", [])):
        con.execute(f"INSERT INTO bands VALUES ({placeholders})", values)
        violations = dict(check_invariants(con, SQL))
    assert violations.get("duplicate_band") == 1


def test_band_out_of_window_is_reported(con):
    mbid = con.execute("SELECT mbid FROM bands LIMIT 1").fetchone()[0]
    original = con.execute("SELECT y0 FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    with restored(con, ("UPDATE bands SET y0 = ? WHERE mbid = ?", [original, mbid])):
        con.execute("UPDATE bands SET y0 = 1700 WHERE mbid = ?", [mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("band_out_of_window") == 1


def test_end_before_begin_is_reported(con):
    mbid = con.execute("SELECT mbid FROM bands WHERE y0 IS NOT NULL LIMIT 1").fetchone()[0]
    y0 = con.execute("SELECT y0 FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    original = con.execute("SELECT y_end FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    with restored(con, ("UPDATE bands SET y_end = ? WHERE mbid = ?", [original, mbid])):
        con.execute("UPDATE bands SET y_end = ? WHERE mbid = ?", [y0 - 1, mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("end_before_begin") == 1


def test_end_after_dump_year_is_reported(con):
    mbid = con.execute("SELECT mbid FROM bands LIMIT 1").fetchone()[0]
    original = con.execute("SELECT y_end_declared FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    with restored(con, ("UPDATE bands SET y_end_declared = ? WHERE mbid = ?", [original, mbid])):
        con.execute("UPDATE bands SET y_end_declared = 2100 WHERE mbid = ?", [mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("end_after_dump_year") == 1


def test_end_before_min_year_is_reported(con):
    # The end's lower bound, the twin of end_after_dump_year: four artists of
    # the reference dump declare an end in 1537, 1761, 1781 and 1814.
    mbid = con.execute("SELECT mbid FROM bands LIMIT 1").fetchone()[0]
    original = con.execute(
        "SELECT y_end_declared, y_end FROM bands WHERE mbid = ?", [mbid]
    ).fetchone()
    with restored(
        con,
        (
            "UPDATE bands SET y_end_declared = ?, y_end = ? WHERE mbid = ?",
            [*original, mbid],
        ),
    ):
        con.execute("UPDATE bands SET y_end_declared = 1537, y_end = 1537 WHERE mbid = ?", [mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("end_before_min_year") == 1


def test_contractual_bounds_are_not_read_from_the_session_variables():
    # Built with dump_year = 2030, the production rules accept Thunder Jolt's
    # declared end in 2027 and Inspiral Carpets' 2027 album, and presence and
    # density stretch past 2026. The invariants must not follow the variable:
    # [1850, 2026] is the reference dump's contract, hardcoded in
    # 90_invariants.sql, and moving to another dump is a deliberate edit there
    # — that edit is the point of the check. Reading getvariable('dump_year')
    # back made all four views agree with whatever the production rules did.
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None, dump_year=2030)
    assert dict(check_invariants(c, SQL)) == {
        "end_after_dump_year": 1,
        "album_out_of_window": 1,
        "presence_out_of_range": 2,
        "density_out_of_range": 7,
    }


def test_last_album_mismatch_is_reported(con):
    mbid = con.execute("SELECT mbid FROM bands WHERE y_last_album IS NOT NULL LIMIT 1").fetchone()[
        0
    ]
    original = con.execute("SELECT y_last_album FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    with restored(con, ("UPDATE bands SET y_last_album = ? WHERE mbid = ?", [original, mbid])):
        con.execute("UPDATE bands SET y_last_album = ? WHERE mbid = ?", [original - 1, mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("last_album_mismatch") == 1


def test_album_out_of_window_is_reported(con):
    rg_mbid = con.execute("SELECT rg_mbid FROM albums LIMIT 1").fetchone()[0]
    original = con.execute("SELECT y FROM albums WHERE rg_mbid = ?", [rg_mbid]).fetchone()[0]
    # 2027: past dump_year (2026) for *any* band, whichever one LIMIT 1
    # returns. 2026 fell within the acceptance window for 133 of the 181
    # fixture bands and only passed by luck of sort order.
    with restored(con, ("UPDATE albums SET y = ? WHERE rg_mbid = ?", [original, rg_mbid])):
        con.execute("UPDATE albums SET y = 2027 WHERE rg_mbid = ?", [rg_mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("album_out_of_window") == 1


def test_album_extra_secondary_type_is_reported(con):
    rg_mbid = con.execute("SELECT rg_mbid FROM albums LIMIT 1").fetchone()[0]
    original = con.execute(
        "SELECT secondary FROM raw_release_groups WHERE mbid = ?", [rg_mbid]
    ).fetchone()[0]
    with restored(
        con,
        ("UPDATE raw_release_groups SET secondary = ? WHERE mbid = ?", [original, rg_mbid]),
    ):
        con.execute("UPDATE raw_release_groups SET secondary = ['Live'] WHERE mbid = ?", [rg_mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("album_extra_secondary_type") == 1


def test_first_album_mismatch_is_reported(con):
    mbid = con.execute("SELECT mbid FROM bands WHERE y_first_album IS NOT NULL LIMIT 1").fetchone()[
        0
    ]
    original = con.execute("SELECT y_first_album FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    with restored(con, ("UPDATE bands SET y_first_album = ? WHERE mbid = ?", [original, mbid])):
        con.execute("UPDATE bands SET y_first_album = ? WHERE mbid = ?", [original - 1, mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("first_album_mismatch") == 1


def test_y0_source_mismatch_is_reported_when_source_disagrees_with_the_value(con):
    mbid = con.execute("SELECT mbid FROM bands WHERE y0_source = 'declared' LIMIT 1").fetchone()[0]
    original = con.execute("SELECT y0 FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    with restored(con, ("UPDATE bands SET y0 = ? WHERE mbid = ?", [original, mbid])):
        con.execute("UPDATE bands SET y0 = ? WHERE mbid = ?", [original - 1, mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("y0_source_mismatch") == 1


def test_y0_source_mismatch_is_reported_when_source_is_null_but_y0_is_not(con):
    mbid = con.execute("SELECT mbid FROM bands WHERE y0_source IS NULL LIMIT 1").fetchone()[0]
    with restored(con, ("UPDATE bands SET y0 = NULL, y0_source = NULL WHERE mbid = ?", [mbid])):
        con.execute("UPDATE bands SET y0 = 1999, y0_source = NULL WHERE mbid = ?", [mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("y0_source_mismatch") == 1


def test_y_end_source_mismatch_is_reported(con):
    mbid = con.execute("SELECT mbid FROM bands WHERE y_end_source = 'declared' LIMIT 1").fetchone()[
        0
    ]
    original = con.execute("SELECT y_end FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    with restored(con, ("UPDATE bands SET y_end = ? WHERE mbid = ?", [original, mbid])):
        con.execute("UPDATE bands SET y_end = ? WHERE mbid = ?", [original - 1, mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("y_end_source_mismatch") == 1


def test_y_end_source_mismatch_catches_a_last_album_label_naming_another_value(con):
    # The shape of the 265 published rows: y_end holds the declared *begin*
    # while y_end_source says 'last_album'. The invariant used to copy the
    # production expression — greatest(y_last_album, coalesce(y0_declared,
    # ...)) — which returns exactly that wrong value, so it stayed empty while
    # its own stated contract was violated. Asserted as a contract
    # ('last_album' => y_end = y_last_album), it fires.
    mbid = con.execute(
        "SELECT mbid FROM bands WHERE y_end_source = 'last_album' LIMIT 1"
    ).fetchone()[0]
    original = con.execute(
        "SELECT y0_declared, y_first_album, y_last_album, y_end FROM bands WHERE mbid = ?", [mbid]
    ).fetchone()
    with restored(
        con,
        (
            "UPDATE bands SET y0_declared = ?, y_first_album = ?, y_last_album = ?, y_end = ? "
            "WHERE mbid = ?",
            [*original, mbid],
        ),
    ):
        con.execute(
            "UPDATE bands SET y0_declared = 2005, y_first_album = NULL, y_last_album = 1959, "
            "y_end = 2005 WHERE mbid = ?",
            [mbid],
        )
        violations = dict(check_invariants(con, SQL))
    assert violations.get("y_end_source_mismatch") == 1


def test_density_population_mismatch_is_reported(con):
    genre_mbid, year, original_present = con.execute(
        "SELECT genre_mbid, year, present FROM density LIMIT 1"
    ).fetchone()
    with restored(
        con,
        (
            "UPDATE density SET present = ? WHERE genre_mbid = ? AND year = ?",
            [original_present, genre_mbid, year],
        ),
    ):
        con.execute(
            "UPDATE density SET present = ? WHERE genre_mbid = ? AND year = ?",
            [original_present + 1, genre_mbid, year],
        )
        violations = dict(check_invariants(con, SQL))
    assert violations.get("density_population_mismatch") == 1


def test_band_genres_out_of_order_is_reported(con):
    mbid = con.execute("SELECT mbid FROM bands WHERE len(genres) > 1 LIMIT 1").fetchone()[0]
    original = con.execute("SELECT genres FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    with restored(con, ("UPDATE bands SET genres = ? WHERE mbid = ?", [original, mbid])):
        con.execute("UPDATE bands SET genres = list_reverse(genres) WHERE mbid = ?", [mbid])
        reversed_genres = con.execute("SELECT genres FROM bands WHERE mbid = ?", [mbid]).fetchone()[
            0
        ]
        violations = dict(check_invariants(con, SQL))
    assume_effective = reversed_genres != original
    assert assume_effective
    assert violations.get("band_genres_out_of_order") == 1


def test_unknown_genre_is_reported(con):
    mbid = con.execute("SELECT mbid FROM bands LIMIT 1").fetchone()[0]
    original = con.execute("SELECT genres FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    with restored(con, ("UPDATE bands SET genres = ? WHERE mbid = ?", [original, mbid])):
        con.execute(
            "UPDATE bands SET genres = list_append(genres, "
            "{'mbid': 'inconnu', 'name': 'x', 'votes': 1}) WHERE mbid = ?",
            [mbid],
        )
        violations = dict(check_invariants(con, SQL))
    assert violations.get("unknown_genre") == 1


def test_unknown_genre_survives_a_null_genre_mbid_in_the_vocabulary(con):
    # Same NULL trap as album_without_band: a NULL genre_mbid in the
    # `genres` subquery used to make NOT IN never true. Demonstrated in
    # review on this exact invariant.
    mbid = con.execute("SELECT mbid FROM bands LIMIT 1").fetchone()[0]
    original = con.execute("SELECT genres FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    with restored(
        con,
        ("UPDATE bands SET genres = ? WHERE mbid = ?", [original, mbid]),
        ("DELETE FROM genres WHERE genre_mbid IS NULL", []),
    ):
        con.execute(
            "UPDATE bands SET genres = list_append(genres, "
            "{'mbid': 'inconnu-null-poison', 'name': 'x', 'votes': 1}) WHERE mbid = ?",
            [mbid],
        )
        con.execute("INSERT INTO genres VALUES (NULL, 'null-poison', 0)")
        violations = dict(check_invariants(con, SQL))
    assert violations.get("unknown_genre") == 1


def test_genre_n_bands_mismatch_is_reported(con):
    genre_mbid = con.execute("SELECT genre_mbid FROM genres LIMIT 1").fetchone()[0]
    original = con.execute(
        "SELECT n_bands FROM genres WHERE genre_mbid = ?", [genre_mbid]
    ).fetchone()[0]
    with restored(
        con, ("UPDATE genres SET n_bands = ? WHERE genre_mbid = ?", [original, genre_mbid])
    ):
        con.execute(
            "UPDATE genres SET n_bands = ? WHERE genre_mbid = ?", [original + 1, genre_mbid]
        )
        violations = dict(check_invariants(con, SQL))
    assert violations.get("genre_n_bands_mismatch") == 1


def test_presence_out_of_range_is_reported(con):
    mbid = con.execute("SELECT mbid FROM presence LIMIT 1").fetchone()[0]
    original = con.execute("SELECT y_presence_end FROM presence WHERE mbid = ?", [mbid]).fetchone()[
        0
    ]
    with restored(con, ("UPDATE presence SET y_presence_end = ? WHERE mbid = ?", [original, mbid])):
        con.execute("UPDATE presence SET y_presence_end = 2100 WHERE mbid = ?", [mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("presence_out_of_range") == 1


def test_presence_end_mismatch_is_reported(con):
    mbid = con.execute("SELECT mbid FROM presence LIMIT 1").fetchone()[0]
    original = con.execute("SELECT y_presence_end FROM bands WHERE mbid = ?", [mbid]).fetchone()[0]
    with restored(con, ("UPDATE bands SET y_presence_end = ? WHERE mbid = ?", [original, mbid])):
        con.execute("UPDATE bands SET y_presence_end = ? WHERE mbid = ?", [original - 1, mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("presence_end_mismatch") == 1


def test_density_out_of_range_is_reported(con):
    row = con.execute("SELECT * FROM density LIMIT 1").fetchone()
    cols = [d[0] for d in con.description]
    genre_mbid = row[cols.index("genre_mbid")]
    with restored(
        con,
        ("DELETE FROM density WHERE genre_mbid = ? AND year = 2100", [genre_mbid]),
    ):
        con.execute(
            f"INSERT INTO density VALUES ({', '.join('?' for _ in cols)})",
            [genre_mbid, 2100, row[cols.index("present")]],
        )
        violations = dict(check_invariants(con, SQL))
    assert violations.get("density_out_of_range") == 1


def test_density_out_of_range_is_reported_below_1850(con):
    row = con.execute("SELECT * FROM density LIMIT 1").fetchone()
    cols = [d[0] for d in con.description]
    genre_mbid = row[cols.index("genre_mbid")]
    with restored(
        con,
        ("DELETE FROM density WHERE genre_mbid = ? AND year = 1700", [genre_mbid]),
    ):
        con.execute(
            f"INSERT INTO density VALUES ({', '.join('?' for _ in cols)})",
            [genre_mbid, 1700, row[cols.index("present")]],
        )
        violations = dict(check_invariants(con, SQL))
    assert violations.get("density_out_of_range") == 1


def test_density_above_band_count_catches_a_genre_absent_from_the_vocabulary(con):
    with restored(con, ("DELETE FROM density WHERE genre_mbid = 'inconnu' AND year = 1900", [])):
        con.execute("INSERT INTO density VALUES ('inconnu', 1900, 1)")
        violations = dict(check_invariants(con, SQL))
    assert violations.get("density_above_band_count") == 1


def test_genre_parent_unknown_genre_is_reported(con):
    with restored(con, ("DELETE FROM genre_parents WHERE genre_mbid = 'inconnu'", [])):
        con.execute("INSERT INTO genre_parents VALUES ('inconnu', 'inconnu-parent', 'wikidata')")
        violations = dict(check_invariants(con, SQL))
    assert violations.get("genre_parent_unknown_genre") == 2


def test_genre_parent_unknown_genre_survives_a_null_genre_mbid_in_the_vocabulary(con):
    # Same NULL trap as album_without_band and unknown_genre: a NULL
    # genre_mbid in the `genres` subquery used to make NOT IN never true.
    with restored(
        con,
        ("DELETE FROM genre_parents WHERE genre_mbid = 'inconnu-null-poison'", []),
        ("DELETE FROM genres WHERE genre_mbid IS NULL", []),
    ):
        con.execute(
            "INSERT INTO genre_parents VALUES "
            "('inconnu-null-poison', 'inconnu-parent-null-poison', 'wikidata')"
        )
        con.execute("INSERT INTO genres VALUES (NULL, 'null-poison', 0)")
        violations = dict(check_invariants(con, SQL))
    assert violations.get("genre_parent_unknown_genre") == 2


def test_genre_parent_cycle_is_reported(con):
    with restored(
        con,
        ("DELETE FROM genre_parents WHERE genre_mbid IN ('cycle-a', 'cycle-b')", []),
        ("DELETE FROM genres WHERE genre_mbid IN ('cycle-a', 'cycle-b')", []),
    ):
        con.execute("INSERT INTO genres VALUES ('cycle-a', 'A', 0), ('cycle-b', 'B', 0)")
        con.execute(
            "INSERT INTO genre_parents VALUES "
            "('cycle-a', 'cycle-b', 'wikidata'), ('cycle-b', 'cycle-a', 'wikidata')"
        )
        violations = dict(check_invariants(con, SQL))
    assert violations.get("genre_parent_cycle") == 2


def test_density_above_band_count_is_reported(con):
    genre_mbid, year, original_present = con.execute(
        "SELECT genre_mbid, year, present FROM density LIMIT 1"
    ).fetchone()
    n_bands = con.execute(
        "SELECT n_bands FROM genres WHERE genre_mbid = ?", [genre_mbid]
    ).fetchone()[0]
    with restored(
        con,
        (
            "UPDATE density SET present = ? WHERE genre_mbid = ? AND year = ?",
            [original_present, genre_mbid, year],
        ),
    ):
        con.execute(
            "UPDATE density SET present = ? WHERE genre_mbid = ? AND year = ?",
            [n_bands + 1, genre_mbid, year],
        )
        violations = dict(check_invariants(con, SQL))
    assert violations.get("density_above_band_count") == 1


def test_member_without_band_is_reported(con):
    with restored(con, ("DELETE FROM members WHERE band_mbid = 'inconnu'", [])):
        con.execute("INSERT INTO members VALUES ('inconnu', 'person', 1999, NULL)")
        violations = dict(check_invariants(con, SQL))
    assert violations.get("member_without_band") == 1


def test_member_without_band_survives_a_null_mbid_in_bands(con):
    # Same NULL trap as album_without_band: a single NULL mbid in the `bands`
    # subquery makes `x NOT IN (subquery)` never true, whatever x is, so the
    # invariant would go silent on every real violation. NOT EXISTS is NULL-safe.
    row = con.execute("SELECT * FROM bands LIMIT 1").fetchone()
    cols = [d[0] for d in con.description]
    values = list(row)
    values[cols.index("mbid")] = None
    placeholders = ", ".join("?" for _ in cols)
    with restored(
        con,
        ("DELETE FROM members WHERE band_mbid = 'inconnu-null-poison'", []),
        ("DELETE FROM bands WHERE mbid IS NULL", []),
    ):
        con.execute("INSERT INTO members VALUES ('inconnu-null-poison', 'person', 1999, NULL)")
        con.execute(f"INSERT INTO bands VALUES ({placeholders})", values)
        violations = dict(check_invariants(con, SQL))
    assert violations.get("member_without_band") == 1


def test_member_without_person_is_reported(con):
    band_mbid = con.execute("SELECT mbid FROM bands LIMIT 1").fetchone()[0]
    with restored(con, ("DELETE FROM members WHERE person_mbid IS NULL", [])):
        con.execute("INSERT INTO members VALUES (?, NULL, 1999, NULL)", [band_mbid])
        violations = dict(check_invariants(con, SQL))
    assert violations.get("member_without_person") == 1


def test_duplicate_member_is_reported(con):
    # NULL years on purpose: a duplicate must be caught on the pair alone,
    # and GROUP BY has to treat two NULL edges as the same relation, exactly
    # as the DISTINCT of 80_members.sql collapses them.
    row = con.execute("SELECT * FROM members LIMIT 1").fetchone()
    placeholders = ", ".join("?" for _ in row)
    with restored(con, ("DELETE FROM members WHERE person_mbid = 'duplicate-person'", [])):
        for _ in range(2):
            con.execute(
                f"INSERT INTO members VALUES ({placeholders})",
                [row[0], "duplicate-person", None, None],
            )
        violations = dict(check_invariants(con, SQL))
    assert violations.get("duplicate_member") == 1


def test_corrections_file_too_large_is_reported(con):
    with restored(con, ("DELETE FROM corrections", [])):
        con.execute(
            "INSERT INTO corrections SELECT 'm' || i, 'begin', '2000', 'j', 's' "
            "FROM range(51) AS t(i)"
        )
        violations = dict(check_invariants(con, SQL))
    assert violations.get("corrections_file_too_large") == 1


def test_corrections_invalid_is_reported(con):
    # Three real silent no-ops: an unknown mbid, a misspelled field (typo),
    # and a field unsupported by apply_corrections.
    mbid = con.execute("SELECT mbid FROM bands LIMIT 1").fetchone()[0]
    with restored(
        con,
        (
            "DELETE FROM corrections WHERE mbid = 'inconnu' OR field IN ('Begin', 'country')",
            [],
        ),
    ):
        con.execute(
            "INSERT INTO corrections VALUES "
            "('inconnu', 'begin', '2000', 'j', 's'), "
            f"('{mbid}', 'Begin', '2000', 'j', 's'), "
            f"('{mbid}', 'country', 'FR', 'j', 's')"
        )
        violations = dict(check_invariants(con, SQL))
    assert violations.get("corrections_invalid") == 3


def test_corrections_invalid_survives_a_null_mbid_in_raw_artists(con):
    # Same NULL trap as album_without_band and unknown_genre: a NULL mbid
    # in the `raw_artists` subquery used to make NOT IN never true.
    with restored(
        con,
        ("DELETE FROM raw_artists WHERE mbid IS NULL", []),
        ("DELETE FROM corrections WHERE mbid = 'inconnu-null-poison'", []),
    ):
        con.execute(
            "INSERT INTO raw_artists VALUES "
            "(NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)"
        )
        con.execute(
            "INSERT INTO corrections VALUES ('inconnu-null-poison', 'begin', '2000', 'j', 's')"
        )
        violations = dict(check_invariants(con, SQL))
    assert violations.get("corrections_invalid") == 1
