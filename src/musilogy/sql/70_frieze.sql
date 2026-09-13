-- The display projection: one row per band the frieze can draw, in the order
-- it draws them. Deliberately narrower than `bands` and exactly as wide as
-- `density`'s population — a band absent from density has no cell to sit in,
-- and showing it would make the two views disagree on what exists.
--
-- `i` is the identity the published blobs use. Bands travel as a row index
-- rather than an mbid because 36-byte UUIDs are half the payload and are only
-- needed to open MusicBrainz; 85_lineage.sql references this same `i`.
CREATE OR REPLACE TABLE frieze AS
WITH eligible AS (
  SELECT DISTINCT b.mbid
  FROM bands b, UNNEST(b.genres) AS t(g)
  JOIN genres gx ON gx.genre_mbid = t.g.mbid
  WHERE b.y0 IS NOT NULL AND b.type = 'Group' AND gx.density_eligible
),
counted AS (
  SELECT band_mbid, count(*) AS n FROM albums GROUP BY band_mbid
)
SELECT
  (row_number() OVER (ORDER BY b.y0, b.mbid) - 1)::BIGINT AS i,
  b.mbid,
  b.name,
  b.y0::SMALLINT AS y0,
  b.y_presence_end::SMALLINT AS y1,
  coalesce(b.ended, false) AS ended,
  -- Published beside y1 because y_presence_end collapses to y0 when the end is
  -- unknown: without this flag the frieze draws a one-year bar and asserts an
  -- end the source never declared.
  b.y_end_source = 'declared' AS y_end_declared,
  -- The rank key. Album count is carried by the source; a notoriety score
  -- would have to be invented, and the frieze can only show a few hundred
  -- bands at once so the choice has to be defensible.
  least(coalesce(c.n, 0), 255)::UTINYINT AS n_albums
FROM bands b
SEMI JOIN eligible e ON e.mbid = b.mbid
LEFT JOIN counted c ON c.band_mbid = b.mbid;
