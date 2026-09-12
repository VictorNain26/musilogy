-- R7. La fin déclarée fait foi ; sinon le dernier album, jamais avant la formation.
CREATE OR REPLACE TABLE presence AS
SELECT
  mbid,
  y0,
  least(
    getvariable('dump_year'),
    CASE WHEN y_end_declared IS NOT NULL THEN y_end_declared
         -- coalesce explicite : sans lui, la formule dépendrait du fait que
         -- greatest() de DuckDB ignore les NULL plutôt que de les propager.
         ELSE greatest(y0, coalesce(y_last_album, y0)) END
  ) AS y_presence_end
FROM bands;

-- Publiée sur bands : sans elle, la couche 1 réimplémenterait R7.
ALTER TABLE bands ADD COLUMN y_presence_end INTEGER;
UPDATE bands SET y_presence_end = (
  SELECT p.y_presence_end FROM presence p WHERE p.mbid = bands.mbid
);
