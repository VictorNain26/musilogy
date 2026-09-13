-- Lineage between bands, derived from the musicians they share. This is not
-- influence: MusicBrainz carries no influence relationship, Wikidata's P737
-- covers 624 bands of 682 447 and DBpedia's influencedBy none at all. What the
-- source does carry is who played where, and two bands sharing a musician are
-- linked by a fact the reader can check — which is the only claim this table
-- makes.
--
-- Restricted to `frieze` on both ends: an edge toward a band the frieze cannot
-- draw has nowhere to land.
CREATE OR REPLACE TABLE lineage AS
WITH m AS (
  SELECT f.i, f.y0, r.person_mbid
  FROM members r JOIN frieze f ON f.mbid = r.band_mbid
)
SELECT
  a.i AS src,
  b.i AS dst,
  least(count(DISTINCT a.person_mbid), 255)::UTINYINT AS shared
FROM m a JOIN m b ON a.person_mbid = b.person_mbid
-- Oriented by formation year, and only when the years differ: equal years give
-- no precedence, and the pair is dropped rather than ordered arbitrarily.
WHERE a.y0 < b.y0
GROUP BY a.i, b.i;
