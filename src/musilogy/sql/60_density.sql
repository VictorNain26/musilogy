-- R7, aggregate. Deliberately narrower than the population: only bands of
-- type Group, with a non-NULL y0, that carry at least one genre. Per-genre
-- totals do not add up: a band counts in each of them.
CREATE OR REPLACE TABLE density AS
SELECT g.mbid AS genre_mbid, y.year, count(*) AS present
FROM presence p
JOIN bands b USING (mbid),
     UNNEST(b.genres) AS t(g),
     range(getvariable('min_year'), getvariable('dump_year') + 1) AS y(year)
WHERE b.type = 'Group'
  AND y.year BETWEEN p.y0 AND p.y_presence_end
  -- Genres the multi-artist rule of 20_albums.sql mostly destroys are dropped
  -- here and only here: bands, albums, genres and members keep every one of
  -- them, because population and projection are two different things. The two
  -- bounds are session variables set by build(), the rate itself is measured
  -- in 55_genre_reliability.sql. NOT EXISTS rather than a negated comparison:
  -- a genre whose rate is NULL (no candidate release-group at all) must stay,
  -- not be silenced by three-valued logic.
  AND NOT EXISTS (
    SELECT 1 FROM genres gx
    WHERE gx.genre_mbid = t.g.mbid
      AND gx.multi_artist_drop_pct >= getvariable('multi_artist_drop_limit')
      AND gx.n_candidate_albums >= getvariable('min_candidate_albums')
  )
GROUP BY g.mbid, y.year;
