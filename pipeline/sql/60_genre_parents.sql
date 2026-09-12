-- §6. Multivalued relation: a genre can have several asserted parents.
CREATE OR REPLACE TABLE genre_parents AS
SELECT DISTINCT w.mbid AS genre_mbid, w.parentMbid AS parent_mbid, 'wikidata' AS source
FROM read_csv('pipeline/reference/20260912-wikidata-genre-parents.csv', header=true) w
WHERE w.parentMbid IS NOT NULL
  AND w.mbid IN (SELECT genre_mbid FROM genres)
  AND w.parentMbid IN (SELECT genre_mbid FROM genres)
  AND w.mbid <> w.parentMbid;
