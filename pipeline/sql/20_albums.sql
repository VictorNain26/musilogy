-- R3. Les types secondaires sont vides ou exactement {Soundtrack}.
CREATE OR REPLACE TABLE albums AS
SELECT
  b.mbid AS band_mbid,
  r.mbid AS rg_mbid,
  r.title,
  yr(r.date) AS y,
  list_contains(coalesce(r.secondary, []), 'Soundtrack') AS soundtrack
FROM raw_release_groups r
JOIN bands b ON b.mbid = list_distinct(r.artists)[1]
WHERE len(list_distinct(r.artists)) = 1
  AND yr(r.date) IS NOT NULL
  AND yr(r.date) <= getvariable('dump_year')
  AND len(list_filter(coalesce(r.secondary, []), s -> s <> 'Soundtrack')) = 0
  AND yr(r.date) BETWEEN b.y0 - 5
                     AND coalesce(b.y_end_declared, getvariable('dump_year')) + 5;

ALTER TABLE bands ADD COLUMN y_last_album INTEGER;
UPDATE bands SET y_last_album = (
  SELECT max(a.y) FROM albums a WHERE a.band_mbid = bands.mbid
);
