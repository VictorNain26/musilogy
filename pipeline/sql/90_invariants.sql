-- Each view must be empty. The view's name is the invariant's name.
-- Unique and non-null mbid (spec §9.2): a NULL mbid is a violation even
-- alone, group by NULL does not let it slip through under count(*) = 1.
CREATE OR REPLACE VIEW duplicate_band AS
  SELECT mbid FROM bands GROUP BY mbid HAVING count(*) > 1 OR mbid IS NULL;
-- 1850 is hardcoded here on purpose, independently of the min_year session
-- variable used by 10_bands.sql: this invariant re-asserts the contractual
-- bound, it must not read it back from the same variable the production
-- rule relies on, or a wrong variable value would satisfy both silently.
CREATE OR REPLACE VIEW band_out_of_window AS
  SELECT mbid FROM bands WHERE y0 IS NULL OR y0 < 1850 OR y0 > getvariable('dump_year');
-- Split in two: an end before the start and an end after the dump are
-- two unrelated anomalies, a single name would hide which one broke.
CREATE OR REPLACE VIEW end_before_begin AS
  SELECT mbid FROM bands WHERE y_end_declared IS NOT NULL AND y_end_declared < y0;
CREATE OR REPLACE VIEW end_after_dump_year AS
  SELECT mbid FROM bands
  WHERE y_end_declared IS NOT NULL AND y_end_declared > getvariable('dump_year');
CREATE OR REPLACE VIEW last_album_mismatch AS
  SELECT b.mbid FROM bands b
  WHERE b.y_last_album IS DISTINCT FROM
        (SELECT max(a.y) FROM albums a WHERE a.band_mbid = b.mbid);
-- NOT EXISTS, not NOT IN: a single NULL mbid returned by the subquery would
-- make NOT IN never true, silencing this invariant forever.
CREATE OR REPLACE VIEW album_without_band AS
  SELECT rg_mbid FROM albums a
  WHERE NOT EXISTS (SELECT 1 FROM bands b WHERE b.mbid = a.band_mbid);
CREATE OR REPLACE VIEW album_out_of_window AS
  SELECT a.rg_mbid FROM albums a JOIN bands b ON b.mbid = a.band_mbid
  WHERE a.y NOT BETWEEN b.y0 - 5 AND coalesce(b.y_end_declared, getvariable('dump_year')) + 5
     OR a.y > getvariable('dump_year');
-- §9.2. `albums` does not keep the secondary types; re-checked via
-- rg_mbid against raw_release_groups, which stays available after the build.
CREATE OR REPLACE VIEW album_extra_secondary_type AS
  SELECT a.rg_mbid FROM albums a JOIN raw_release_groups r ON r.mbid = a.rg_mbid
  WHERE len(list_filter(coalesce(r.secondary, []), s -> s <> 'Soundtrack')) > 0;
CREATE OR REPLACE VIEW band_without_genre AS
  SELECT mbid FROM bands WHERE len(genres) = 0;
-- Independent of the sort applied at construction time (10_bands.sql):
-- compares each adjacent pair, does not reuse bands' sort formula.
CREATE OR REPLACE VIEW band_genres_out_of_order AS
  SELECT mbid FROM bands
  WHERE len(genres) > 1
    AND EXISTS (
      SELECT 1 FROM range(1, len(genres)) AS t(i)
      WHERE genres[i + 1].votes > genres[i].votes
         OR (genres[i + 1].votes = genres[i].votes AND genres[i + 1].name < genres[i].name)
    );
-- NOT EXISTS, not NOT IN: see album_without_band above, same NULL trap.
CREATE OR REPLACE VIEW unknown_genre AS
  SELECT t.g.mbid FROM (SELECT unnest(genres) AS g FROM bands) t
  WHERE NOT EXISTS (SELECT 1 FROM genres g WHERE g.genre_mbid = t.g.mbid);
-- §9.2. Independent recomputation, same rationale as last_album_mismatch.
CREATE OR REPLACE VIEW genre_n_bands_mismatch AS
  SELECT g.genre_mbid FROM genres g
  WHERE g.n_bands <> (
    SELECT count(*) FROM bands b, UNNEST(b.genres) AS t(x) WHERE t.x.mbid = g.genre_mbid
  );
CREATE OR REPLACE VIEW presence_out_of_range AS
  SELECT p.mbid FROM presence p JOIN bands b USING (mbid)
  WHERE p.y_presence_end < p.y0 OR p.y_presence_end > getvariable('dump_year')
     OR (b.y_end_declared IS NOT NULL AND p.y_presence_end <> b.y_end_declared);
-- Same idiom as 20_albums.sql/last_album_mismatch, for its twin
-- 30_presence.sql: bands.y_presence_end (published in Parquet and
-- web/bands.json.gz) must stay identical to presence.y_presence_end (from
-- which density derives), otherwise the two published artifacts could diverge.
CREATE OR REPLACE VIEW presence_end_mismatch AS
  SELECT b.mbid FROM bands b JOIN presence p USING (mbid)
  WHERE b.y_presence_end IS DISTINCT FROM p.y_presence_end;
-- 1850 hardcoded on purpose, same reasoning as band_out_of_window above.
CREATE OR REPLACE VIEW density_out_of_range AS
  SELECT genre_mbid FROM density WHERE year > getvariable('dump_year') OR year < 1850;
-- LEFT JOIN: a genre_mbid absent from the vocabulary must not make the
-- density row disappear from its own check.
CREATE OR REPLACE VIEW density_above_band_count AS
  SELECT d.genre_mbid FROM density d LEFT JOIN genres g USING (genre_mbid)
  WHERE g.genre_mbid IS NULL OR d.present > g.n_bands;
-- §9.2. genre_parents references existing genres at both ends.
-- NOT EXISTS, not NOT IN: see album_without_band above, same NULL trap.
CREATE OR REPLACE VIEW genre_parent_unknown_genre AS
  SELECT genre_mbid FROM genre_parents gp
  WHERE NOT EXISTS (SELECT 1 FROM genres g WHERE g.genre_mbid = gp.genre_mbid)
  UNION
  SELECT parent_mbid FROM genre_parents gp
  WHERE NOT EXISTS (SELECT 1 FROM genres g WHERE g.genre_mbid = gp.parent_mbid);
-- §9.2. genre_parents has no cycle. The path walked by the recursive CTE
-- never revisits an already-visited node: its length is bounded by the
-- number of genres, so the query terminates whether the graph is cyclic or not.
CREATE OR REPLACE VIEW genre_parent_cycle AS
  WITH RECURSIVE walk(start_mbid, path, current_mbid, cycle) AS (
    SELECT genre_mbid, [genre_mbid], parent_mbid, (genre_mbid = parent_mbid)
    FROM genre_parents
    UNION ALL
    SELECT w.start_mbid,
           list_append(w.path, w.current_mbid),
           gp.parent_mbid,
           list_contains(w.path, gp.parent_mbid) OR gp.parent_mbid = w.current_mbid
    FROM walk w JOIN genre_parents gp ON gp.genre_mbid = w.current_mbid
    WHERE NOT w.cycle
  )
  SELECT DISTINCT start_mbid AS genre_mbid FROM walk WHERE cycle;
-- §9.2. corrections.csv holds at most 50 rows; materialized even empty
-- by apply_corrections, so available without depending on the dump.
CREATE OR REPLACE VIEW corrections_file_too_large AS
  SELECT count(*) AS n FROM corrections HAVING count(*) > 50;
-- A row that touches no raw_artists, or carries a field outside {begin,
-- end}, is loaded (counts toward the 50-row cap) without ever changing
-- anything: a silent no-op, not a correction.
-- NOT EXISTS for the mbid check, not NOT IN: see album_without_band above,
-- same NULL trap (raw_artists.mbid is never NULL in practice, but nothing
-- guarantees it, and this check must not rely on that).
CREATE OR REPLACE VIEW corrections_invalid AS
  SELECT c.mbid, c.field FROM corrections c
  WHERE c.field NOT IN ('begin', 'end')
     OR NOT EXISTS (SELECT 1 FROM raw_artists r WHERE r.mbid = c.mbid);
