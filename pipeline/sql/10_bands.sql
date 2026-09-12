-- R1 population, R2 dates. dump_year is provided by build() via SET VARIABLE.
-- The five boolean columns carry the R2 sub-rules: they decide nothing
-- beyond y0/y_end_declared, they just name the same decision so that
-- publish.py can count it without recomputing it.
CREATE OR REPLACE TABLE dated AS
SELECT
  mbid, name, type, ended, country, begin_area, genres, members,
  CASE WHEN yr(begin) <= getvariable('dump_year') THEN yr(begin) END AS y0,
  CASE WHEN yr("end") <= getvariable('dump_year')
        AND (yr(begin) IS NULL OR yr("end") >= yr(begin))
       THEN yr("end") END AS y_end_declared,
  begin IS NOT NULL AND yr(begin) IS NULL AS begin_illegible,
  "end" IS NOT NULL AND yr("end") IS NULL AS end_illegible,
  yr(begin) IS NOT NULL AND yr(begin) > getvariable('dump_year') AS begin_future,
  yr("end") IS NOT NULL AND yr("end") > getvariable('dump_year') AS end_future,
  yr(begin) IS NOT NULL AND yr("end") IS NOT NULL
    AND yr("end") <= getvariable('dump_year')
    AND yr("end") < yr(begin) AS end_before_begin
FROM raw_artists;

-- R2 counters for manifest.json (§5.3): population = raw_artists, i.e.
-- every group/orchestra/choir extracted, not just `bands` after R1 — a
-- group without a genre but with an illegible end must still be visible here.
CREATE OR REPLACE TABLE r2_anomalies AS
SELECT
  sum(begin_illegible::INTEGER) AS begin_illegible,
  sum(end_illegible::INTEGER) AS end_illegible,
  sum(begin_future::INTEGER) AS begin_future,
  sum(end_future::INTEGER) AS end_future,
  sum(end_before_begin::INTEGER) AS end_before_begin
FROM dated;

CREATE OR REPLACE TABLE bands AS
SELECT mbid, name, y0, y_end_declared, ended, country, begin_area,
  -- R5. Explicit sort (votes descending, then name), never inherited from
  -- the source (alphabetical). list_sort does not accept a lambda comparator
  -- in 1.5.5: sort by key, projecting each genre onto {k: [-votes], n: name,
  -- v: genre}, list_sort compares structs field by field.
  list_transform(
    list_sort(list_transform(genres, x -> {'k': [-x.votes::INT], 'n': x.name, 'v': x})),
    y -> y.v
  ) AS genres
FROM dated
WHERE type = 'Group'
  AND y0 BETWEEN getvariable('min_year') AND getvariable('dump_year')
  AND len(genres) > 0;
