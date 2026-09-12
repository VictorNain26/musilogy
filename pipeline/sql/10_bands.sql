-- R1 population, R2 dates. dump_year est fourni par build() via SET VARIABLE.
-- Les cinq colonnes booléennes portent les sous-règles R2 : elles ne
-- décident rien de plus que y0/y_end_declared, elles nomment la même
-- décision pour que publish.py puisse la compter sans la recalculer.
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

-- Compteurs R2 pour manifest.json (§5.3) : population = raw_artists, soit
-- tous les groupes/orchestres/chœurs extraits, pas seulement `bands` après
-- R1 — un groupe sans genre avec une fin illisible doit rester visible ici.
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
  -- R5. Tri posé (votes décroissants puis nom), jamais hérité de la source
  -- (alphabétique). list_sort n'accepte pas de comparateur lambda en 1.5.5 :
  -- on trie par clé en projetant chaque genre sur {k: [-votes], n: name, v:
  -- genre}, list_sort comparant les structs champ par champ.
  list_transform(
    list_sort(list_transform(genres, x -> {'k': [-x.votes::INT], 'n': x.name, 'v': x})),
    y -> y.v
  ) AS genres
FROM dated
WHERE type = 'Group'
  AND y0 BETWEEN 1850 AND getvariable('dump_year')
  AND len(genres) > 0;
