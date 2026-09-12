from conftest import build_synthetic, synthetic_artist

DISINCARNATE = "a9424175-8b06-44ad-a1f4-319e92a50879"
JOY_DIVISION = "9a58fda3-f4ed-4080-a3a5-f457aac9fcdd"
CLEEF = "1434b0d0-d647-421e-b345-1b9847045a52"


def test_a_witness_relations_land_with_their_person_and_their_years(con):
    # Disincarnate's two relations, transcribed as literals from the witness:
    # one closed (1991-1991), one still open (1992, no end). Re-reading them
    # from raw_artists the way 80_members.sql does would compare the table to
    # itself and pass whatever the rule computes.
    assert con.execute(
        "SELECT person_mbid, y_begin, y_end FROM members WHERE band_mbid = ? ORDER BY person_mbid",
        [DISINCARNATE],
    ).fetchall() == [
        ("5b640e8d-bcb8-45be-a32e-8f4325c8d6c9", 1991, 1991),
        ("986259e3-dd6c-49a7-8679-e8cf48e799c9", 1992, None),
    ]


def test_a_month_precision_date_reads_its_year_and_a_missing_edge_stays_null(con):
    # Joy Division's four relations all end "1980-05" with no begin: the year
    # is the first four characters, and an absent edge stays absent rather
    # than being filled with the band's own dates.
    assert con.execute(
        "SELECT DISTINCT y_begin, y_end FROM members WHERE band_mbid = ?", [JOY_DIVISION]
    ).fetchall() == [(None, 1980)]


def test_identical_relations_collapse_to_one_row(con):
    # Cleef credits the same person twice with the same (absent) dates — the
    # dump emits one relation per set of attributes. Without DISTINCT this
    # witness alone publishes the same relation twice.
    assert con.execute("SELECT count(*) FROM members WHERE band_mbid = ?", [CLEEF]).fetchall() == [
        (1,)
    ]
    assert con.execute(
        "SELECT count(*) FROM members WHERE band_mbid = ? AND person_mbid = ?",
        [CLEEF, "1b850cda-5579-4be6-bd51-a6b6fb3ccb2b"],
    ).fetchall() == [(1,)]


def test_an_illegible_relation_date_becomes_null_instead_of_being_guessed(tmp_path):
    # "????-01" is a real shape: five relations of the reference dump carry it.
    # No witness does, hence the synthetic record. A direct CAST would raise
    # or invent a year; the relation must survive with a NULL edge.
    c = build_synthetic(
        tmp_path,
        [
            synthetic_artist(
                "band",
                "1990",
                None,
                members=[{"mbid": "person", "begin": "????-01", "end": "1995"}],
            )
        ],
    )
    assert c.execute("SELECT person_mbid, y_begin, y_end FROM members").fetchall() == [
        ("person", None, 1995)
    ]


def test_a_relation_without_a_person_is_dropped_and_its_siblings_kept(tmp_path):
    # The second relation is there on purpose: without it the assertion would
    # also hold if the whole band had been dropped from the table.
    c = build_synthetic(
        tmp_path,
        [
            synthetic_artist(
                "band",
                "1990",
                None,
                members=[
                    {"mbid": None, "begin": "1990", "end": None},
                    {"mbid": "person", "begin": "1990", "end": None},
                ],
            )
        ],
    )
    assert c.execute("SELECT person_mbid FROM members").fetchall() == [("person",)]
