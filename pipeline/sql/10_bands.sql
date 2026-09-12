-- R1 population, R2 dates. dump_year est fourni par build() via SET VARIABLE.
CREATE OR REPLACE TABLE dated AS
SELECT
  mbid, name, type, ended, country, begin_area, genres, members,
  CASE WHEN yr(begin) <= getvariable('dump_year') THEN yr(begin) END AS y0,
  CASE WHEN yr("end") <= getvariable('dump_year')
        AND (yr(begin) IS NULL OR yr("end") >= yr(begin))
       THEN yr("end") END AS y_end_declared
FROM raw_artists;

CREATE OR REPLACE TABLE bands AS
SELECT mbid, name, y0, y_end_declared, ended, country, begin_area, genres
FROM dated
WHERE type = 'Group'
  AND y0 BETWEEN 1850 AND getvariable('dump_year')
  AND len(genres) > 0;
