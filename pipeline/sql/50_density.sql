-- R7, aggregate. Per-genre totals do not add up: a band counts in each of them.
CREATE OR REPLACE TABLE density AS
SELECT g.mbid AS genre_mbid, y.year, count(*) AS present
FROM presence p
JOIN bands b USING (mbid),
     UNNEST(b.genres) AS t(g),
     range(getvariable('min_year'), getvariable('dump_year') + 1) AS y(year)
WHERE y.year BETWEEN p.y0 AND p.y_presence_end
GROUP BY g.mbid, y.year;
