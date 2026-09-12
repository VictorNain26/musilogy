-- R3. Les types secondaires sont vides ou exactement {Soundtrack}.
CREATE OR REPLACE TABLE albums AS
SELECT
  b.mbid AS band_mbid,
  r.mbid AS rg_mbid,
  r.title,
  yr(r.date) AS y,
  len(coalesce(r.secondary, [])) = 1 AS soundtrack
FROM raw_release_groups r
JOIN bands b ON b.mbid = list_distinct(r.artists)[1]
WHERE len(list_distinct(r.artists)) = 1
  AND yr(r.date) IS NOT NULL
  AND yr(r.date) <= getvariable('dump_year')
  AND len(list_filter(coalesce(r.secondary, []), s -> s <> 'Soundtrack')) = 0
  AND yr(r.date) BETWEEN b.y0 - 5
                     AND coalesce(b.y_end_declared, getvariable('dump_year')) + 5;
