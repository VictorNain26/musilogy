def test_frieze_holds_only_bands_density_can_place(con):
    rows = con.execute("""
        SELECT count(*) FROM frieze f
        WHERE f.y0 IS NULL OR f.mbid NOT IN (SELECT mbid FROM bands WHERE type = 'Group')
    """).fetchone()
    assert rows[0] == 0


def test_frieze_excludes_bands_whose_only_genres_are_ineligible(con):
    # A band kept in `bands` but carrying no publishable genre has no cell in
    # density; showing it on the frieze would make the two views disagree on
    # the population.
    orphans = con.execute("""
        SELECT count(*) FROM frieze f WHERE NOT EXISTS (
          SELECT 1 FROM bands b, UNNEST(b.genres) AS t(g)
          JOIN genres gx ON gx.genre_mbid = t.g.mbid
          WHERE b.mbid = f.mbid AND gx.density_eligible)
    """).fetchone()
    assert orphans[0] == 0


def test_frieze_index_is_dense_and_ordered_by_formation(con):
    n, lo, hi = con.execute("SELECT count(*), min(i), max(i) FROM frieze").fetchone()
    assert (lo, hi) == (0, n - 1)
    ordered = con.execute("SELECT i FROM frieze ORDER BY y0, mbid").fetchall()
    assert [r[0] for r in ordered] == list(range(n))


def test_frieze_album_count_saturates_at_255(con):
    over = con.execute("SELECT count(*) FROM frieze WHERE n_albums > 255").fetchone()
    assert over[0] == 0
    matches = con.execute("""
        SELECT count(*) FROM frieze f
        LEFT JOIN (SELECT band_mbid, count(*) n FROM albums GROUP BY 1) a
          ON a.band_mbid = f.mbid
        WHERE f.n_albums <> least(coalesce(a.n, 0), 255)
    """).fetchone()
    assert matches[0] == 0
