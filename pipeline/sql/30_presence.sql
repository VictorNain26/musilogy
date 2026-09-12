-- R7. The declared end is authoritative; otherwise the last album, never before formation.
CREATE OR REPLACE TABLE presence AS
SELECT
  mbid,
  y0,
  least(
    getvariable('dump_year'),
    CASE WHEN y_end_declared IS NOT NULL THEN y_end_declared
         -- explicit coalesce: without it, the formula would depend on
         -- DuckDB's greatest() ignoring NULLs rather than propagating them.
         ELSE greatest(y0, coalesce(y_last_album, y0)) END
  ) AS y_presence_end
FROM bands;

-- Published on bands: without it, layer 1 would have to reimplement R7.
ALTER TABLE bands ADD COLUMN y_presence_end INTEGER;
UPDATE bands SET y_presence_end = (
  SELECT p.y_presence_end FROM presence p WHERE p.mbid = bands.mbid
);
