from conftest import build_synthetic, synthetic_artist

GENRE = [{"mbid": "g-lineage", "name": "lineage", "votes": 1}]


def test_lineage_orientation_requires_the_years_to_differ(tmp_path):
    # No same-year pair of the fixtures shares a musician, so the fixture-based
    # test below cannot tell `a.y0 < b.y0` from `a.y0 <= b.y0`. This scenario
    # forces both shapes into one dump: a same-year pair sharing a musician,
    # which must produce no edge, and a different-year pair sharing another
    # musician, which must produce exactly one, oriented from the earlier band.
    c = build_synthetic(
        tmp_path,
        [
            synthetic_artist(
                "same-a", "1985", None, members=[{"mbid": "shared-same"}], genres=GENRE
            ),
            synthetic_artist(
                "same-b", "1985", None, members=[{"mbid": "shared-same"}], genres=GENRE
            ),
            synthetic_artist(
                "early", "1980", None, members=[{"mbid": "shared-diff"}], genres=GENRE
            ),
            synthetic_artist("late", "1990", None, members=[{"mbid": "shared-diff"}], genres=GENRE),
        ],
    )
    same_a_i, same_b_i = (
        c.execute("SELECT i FROM frieze WHERE mbid = ?", [mbid]).fetchone()[0]
        for mbid in ("same-a", "same-b")
    )
    early_i, late_i = (
        c.execute("SELECT i FROM frieze WHERE mbid = ?", [mbid]).fetchone()[0]
        for mbid in ("early", "late")
    )
    assert (
        c.execute(
            "SELECT count(*) FROM lineage WHERE (src, dst) IN ((?, ?), (?, ?))",
            [same_a_i, same_b_i, same_b_i, same_a_i],
        ).fetchone()[0]
        == 0
    )
    assert c.execute(
        "SELECT src, dst FROM lineage WHERE src = ? OR dst = ?", [early_i, early_i]
    ).fetchall() == [(early_i, late_i)]


def test_lineage_edges_point_forward_in_time(con):
    backwards = con.execute("""
        SELECT count(*) FROM lineage l
        JOIN frieze s ON s.i = l.src JOIN frieze t ON t.i = l.dst
        WHERE s.y0 >= t.y0
    """).fetchone()
    assert backwards[0] == 0


def test_lineage_drops_pairs_formed_the_same_year(con):
    # Two bands formed the same year give no direction, and inventing one would
    # assert a precedence the source does not carry.
    same_year = con.execute("""
        SELECT count(*) FROM frieze a JOIN frieze b ON a.y0 = b.y0 AND a.i < b.i
        WHERE EXISTS (
          SELECT 1 FROM members ma JOIN members mb ON ma.person_mbid = mb.person_mbid
          WHERE ma.band_mbid = a.mbid AND mb.band_mbid = b.mbid)
          AND EXISTS (SELECT 1 FROM lineage l WHERE (l.src, l.dst) IN ((a.i, b.i), (b.i, a.i)))
    """).fetchone()
    assert same_year[0] == 0


def test_lineage_counts_distinct_shared_musicians(con):
    wrong = con.execute("""
        SELECT count(*) FROM lineage l
        JOIN frieze s ON s.i = l.src JOIN frieze t ON t.i = l.dst
        WHERE l.shared <> (
          SELECT count(DISTINCT ma.person_mbid) FROM members ma
          JOIN members mb ON ma.person_mbid = mb.person_mbid
          WHERE ma.band_mbid = s.mbid AND mb.band_mbid = t.mbid)
    """).fetchone()
    assert wrong[0] == 0


def test_lineage_has_no_self_edge_and_no_duplicate(con):
    assert con.execute("SELECT count(*) FROM lineage WHERE src = dst").fetchone()[0] == 0
    assert (
        con.execute(
            "SELECT count(*) FROM (SELECT src, dst FROM lineage GROUP BY 1,2 HAVING count(*) > 1)"
        ).fetchone()[0]
        == 0
    )
