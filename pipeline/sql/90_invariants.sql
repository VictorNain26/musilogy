-- Chaque vue doit être vide. Le nom de la vue est le nom de l'invariant.
-- MBID unique et non nul (spec §9.2) : un mbid NULL vaut violation même
-- seul, group by NULL ne le laisse pas passer sous count(*) = 1.
CREATE OR REPLACE VIEW duplicate_band AS
  SELECT mbid FROM bands GROUP BY mbid HAVING count(*) > 1 OR mbid IS NULL;
CREATE OR REPLACE VIEW band_out_of_window AS
  SELECT mbid FROM bands WHERE y0 IS NULL OR y0 < 1850 OR y0 > getvariable('dump_year');
-- Scindé en deux : une fin antérieure au début et une fin après le dump sont
-- deux anomalies sans rapport, un nom unique masquerait laquelle a cassé.
CREATE OR REPLACE VIEW end_before_begin AS
  SELECT mbid FROM bands WHERE y_end_declared IS NOT NULL AND y_end_declared < y0;
CREATE OR REPLACE VIEW end_after_dump_year AS
  SELECT mbid FROM bands
  WHERE y_end_declared IS NOT NULL AND y_end_declared > getvariable('dump_year');
CREATE OR REPLACE VIEW last_album_mismatch AS
  SELECT b.mbid FROM bands b
  WHERE b.y_last_album IS DISTINCT FROM
        (SELECT max(a.y) FROM albums a WHERE a.band_mbid = b.mbid);
CREATE OR REPLACE VIEW album_without_band AS
  SELECT rg_mbid FROM albums WHERE band_mbid NOT IN (SELECT mbid FROM bands);
CREATE OR REPLACE VIEW album_out_of_window AS
  SELECT a.rg_mbid FROM albums a JOIN bands b ON b.mbid = a.band_mbid
  WHERE a.y NOT BETWEEN b.y0 - 5 AND coalesce(b.y_end_declared, getvariable('dump_year')) + 5
     OR a.y > getvariable('dump_year');
-- §9.2. `albums` ne conserve pas les types secondaires ; revérifié par
-- rg_mbid contre raw_release_groups, qui reste disponible après le build.
CREATE OR REPLACE VIEW album_extra_secondary_type AS
  SELECT a.rg_mbid FROM albums a JOIN raw_release_groups r ON r.mbid = a.rg_mbid
  WHERE len(list_filter(coalesce(r.secondary, []), s -> s <> 'Soundtrack')) > 0;
CREATE OR REPLACE VIEW band_without_genre AS
  SELECT mbid FROM bands WHERE len(genres) = 0;
-- Indépendant du tri appliqué à la construction (10_bands.sql) : compare
-- chaque paire adjacente, ne réutilise pas la formule de tri de bands.
CREATE OR REPLACE VIEW band_genres_out_of_order AS
  SELECT mbid FROM bands
  WHERE len(genres) > 1
    AND EXISTS (
      SELECT 1 FROM range(1, len(genres)) AS t(i)
      WHERE genres[i + 1].votes > genres[i].votes
         OR (genres[i + 1].votes = genres[i].votes AND genres[i + 1].name < genres[i].name)
    );
CREATE OR REPLACE VIEW unknown_genre AS
  SELECT t.g.mbid FROM (SELECT unnest(genres) AS g FROM bands) t
  WHERE t.g.mbid NOT IN (SELECT genre_mbid FROM genres);
-- §9.2. Recalcul indépendant, même motif que last_album_mismatch.
CREATE OR REPLACE VIEW genre_n_bands_mismatch AS
  SELECT g.genre_mbid FROM genres g
  WHERE g.n_bands <> (
    SELECT count(*) FROM bands b, UNNEST(b.genres) AS t(x) WHERE t.x.mbid = g.genre_mbid
  );
CREATE OR REPLACE VIEW presence_out_of_range AS
  SELECT p.mbid FROM presence p JOIN bands b USING (mbid)
  WHERE p.y_presence_end < p.y0 OR p.y_presence_end > getvariable('dump_year')
     OR (b.y_end_declared IS NOT NULL AND p.y_presence_end <> b.y_end_declared);
CREATE OR REPLACE VIEW density_out_of_range AS
  SELECT genre_mbid FROM density WHERE year > getvariable('dump_year');
CREATE OR REPLACE VIEW density_above_band_count AS
  SELECT d.genre_mbid FROM density d JOIN genres g USING (genre_mbid)
  WHERE d.present > g.n_bands;
-- §9.2. genre_parents référence des genres existants aux deux extrémités.
CREATE OR REPLACE VIEW genre_parent_unknown_genre AS
  SELECT genre_mbid FROM genre_parents WHERE genre_mbid NOT IN (SELECT genre_mbid FROM genres)
  UNION
  SELECT parent_mbid FROM genre_parents WHERE parent_mbid NOT IN (SELECT genre_mbid FROM genres);
-- §9.2. genre_parents est sans cycle. Le chemin parcouru par le CTE récursif
-- ne repasse jamais par un nœud déjà visité : sa longueur est bornée par le
-- nombre de genres, donc la requête termine que le graphe soit cyclique ou non.
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
-- §9.2. corrections.csv compte au plus 50 lignes ; materialisée même vide
-- par apply_corrections, donc disponible sans dépendance au dump.
CREATE OR REPLACE VIEW corrections_file_too_large AS
  SELECT count(*) AS n FROM corrections HAVING count(*) > 50;
