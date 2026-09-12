-- R5. Vocabulaire effectivement porté par bands.
CREATE OR REPLACE TABLE genres AS
SELECT g.mbid AS genre_mbid, any_value(g.name) AS name, count(*) AS n_bands
FROM bands, UNNEST(bands.genres) AS t(g)
GROUP BY g.mbid;
