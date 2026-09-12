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
GROUP BY g.mbid, y.year;
