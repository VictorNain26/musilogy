import pytest
from conftest import build_synthetic, unreliable_genre_records


@pytest.fixture(scope="module")
def c(tmp_path_factory):
    artists, release_groups = unreliable_genre_records()
    return build_synthetic(tmp_path_factory.mktemp("reliability"), artists, release_groups)


def measurement(con, genre_mbid):
    return con.execute(
        "SELECT n_candidate_credits, multi_artist_drop_pct FROM genres WHERE genre_mbid = ?",
        [genre_mbid],
    ).fetchone()


def density_rows(con, genre_mbid):
    return con.execute(
        "SELECT count(*) FROM density WHERE genre_mbid = ?", [genre_mbid]
    ).fetchone()[0]


def test_drop_pct_is_the_share_of_candidates_the_multi_artist_rule_removes(c):
    # Three rates on the same shape of data: a measurement that counted
    # release-groups instead of credited (band, genre) rows, or that dropped
    # the multi flag, moves at least one of them.
    assert measurement(c, "g-excluded") == (250, 100.0)
    assert measurement(c, "g-small") == (10, 100.0)
    assert measurement(c, "g-clean") == (250, 0.0)


def test_the_rate_is_measured_on_raw_release_groups_not_on_the_albums_table(c):
    # The crux of the definition. `albums` has already dropped every
    # multi-artist release-group, so band-excluded owns none: a rate computed
    # from `albums` would read 0% (or no row at all) on a genre that in fact
    # loses everything.
    assert c.execute(
        "SELECT count(*) FROM albums WHERE band_mbid = 'band-excluded'"
    ).fetchone() == (0,)
    assert measurement(c, "g-excluded") == (250, 100.0)


def test_a_genre_with_no_candidate_release_group_has_a_count_but_no_rate(c):
    # Zero candidates is a measured fact; the share of zero is not. Publishing
    # 0.0 here would assert a measurement nobody could make.
    assert measurement(c, "g-orphan") == (0, None)


def test_a_genre_over_the_rate_but_under_the_sample_minimum_keeps_its_density(c):
    # g-small loses 100% of its candidates, like g-excluded, and differs from
    # it only by sample size. Drop the minimum from the rule and this fails.
    assert measurement(c, "g-small") == (10, 100.0)
    assert density_rows(c, "g-small") > 0


def test_a_genre_over_both_bounds_leaves_density_but_stays_in_the_vocabulary(c):
    assert density_rows(c, "g-excluded") == 0
    assert c.execute(
        "SELECT name, n_bands FROM genres WHERE genre_mbid = 'g-excluded'"
    ).fetchone() == ("excluded", 2)
    # Control: the rule removes that genre, not the projection as a whole.
    assert density_rows(c, "g-clean") > 0


def test_the_excluded_genre_stays_on_every_population_table(c):
    # Population and projection are different things: the exclusion belongs to
    # density alone. A rule applied one file too early would empty these.
    assert c.execute(
        "SELECT count(*) FROM bands b, UNNEST(b.genres) AS t(g) WHERE t.g.mbid = 'g-excluded'"
    ).fetchone() == (2,)
    assert c.execute(
        "SELECT count(*) FROM bands WHERE mbid IN ('band-excluded', 'band-excluded-2')"
    ).fetchone() == (2,)


def test_the_sample_minimum_is_a_session_variable(tmp_path):
    # Same records, minimum lowered under g-small's 10 candidates: it must now
    # be excluded too. A minimum hardcoded in the SQL would ignore this.
    artists, release_groups = unreliable_genre_records()
    c = build_synthetic(tmp_path, artists, release_groups, min_candidate_credits=5)
    assert density_rows(c, "g-small") == 0
    assert density_rows(c, "g-clean") > 0


def test_the_rate_limit_is_a_session_variable(tmp_path):
    # Limit raised over g-excluded's 100%: nothing is excluded any more, and
    # the genre comes back into density. A limit hardcoded in the SQL would
    # keep it out.
    artists, release_groups = unreliable_genre_records()
    c = build_synthetic(tmp_path, artists, release_groups, multi_artist_drop_limit=100.1)
    assert density_rows(c, "g-excluded") > 0
    assert c.execute("SELECT * FROM density_exclusions").fetchone() == (0, 0)
