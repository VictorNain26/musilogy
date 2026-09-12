-- R7, agrégat. Les totaux par genre ne s'additionnent pas : un groupe compte dans chacun.
CREATE OR REPLACE TABLE density AS
SELECT g.mbid AS genre_mbid, y.year, count(*) AS present
FROM presence p
JOIN bands b USING (mbid),
     UNNEST(b.genres) AS t(g),
     range(1850, getvariable('dump_year') + 1) AS y(year)
WHERE y.year BETWEEN p.y0 AND p.y_presence_end
GROUP BY g.mbid, y.year;
