"""Enchaîne les fichiers SQL de transformation sur une connexion DuckDB."""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

# Chemin résolu depuis ce fichier, pas depuis le cwd du process : le même
# nom relatif est aussi codé en dur dans 60_genre_parents.sql (lu et exécuté
# tel quel par DuckDB), substitué ci-dessous avant exécution pour que les
# deux occurrences pointent la même source, quel que soit le cwd d'appel.
GENRE_PARENTS_CSV = (
    Path(__file__).resolve().parent / "reference" / "20260912-wikidata-genre-parents.csv"
)
GENRE_PARENTS_LITERAL = "pipeline/reference/20260912-wikidata-genre-parents.csv"

RAW_ARTIST_COLUMNS = (
    "{mbid:'VARCHAR', name:'VARCHAR', type:'VARCHAR', begin:'VARCHAR', "
    "\"end\":'VARCHAR', ended:'BOOLEAN', country:'VARCHAR', area:'VARCHAR', "
    "begin_area:'VARCHAR', "
    "genres:'STRUCT(mbid VARCHAR, name VARCHAR, votes INTEGER)[]', "
    "members:'STRUCT(mbid VARCHAR, begin VARCHAR, \"end\" VARCHAR)[]'}"
)
RAW_RG_COLUMNS = (
    "{mbid:'VARCHAR', title:'VARCHAR', date:'VARCHAR', "
    "secondary:'VARCHAR[]', artists:'VARCHAR[]'}"
)


def load_raw(con: duckdb.DuckDBPyConnection, artists: Path, rgs: Path) -> None:
    con.execute(
        f"CREATE OR REPLACE TABLE raw_artists AS SELECT * FROM read_ndjson("
        f"'{artists.as_posix()}', columns={RAW_ARTIST_COLUMNS}, "
        f"format='newline_delimited')"
    )
    con.execute(
        f"CREATE OR REPLACE TABLE raw_release_groups AS SELECT * FROM read_ndjson("
        f"'{rgs.as_posix()}', columns={RAW_RG_COLUMNS}, format='newline_delimited')"
    )


def apply_corrections(con: duckdb.DuckDBPyConnection, corrections: Path | None) -> int:
    if corrections is None:
        # Toujours matérialisée, même vide : la suite rapide (§9.3) construit
        # les fixtures avec corrections=None, et l'invariant
        # corrections_file_too_large lit cette table sans dépendre du dump.
        con.execute(
            "CREATE OR REPLACE TABLE corrections (mbid VARCHAR, field VARCHAR, "
            "value VARCHAR, justification VARCHAR, source VARCHAR)"
        )
        return 0
    con.execute(
        "CREATE OR REPLACE TABLE corrections AS SELECT * FROM read_csv("
        f"'{corrections.as_posix()}', header=true, "
        "columns={mbid:'VARCHAR', field:'VARCHAR', value:'VARCHAR', "
        "justification:'VARCHAR', source:'VARCHAR'})"
    )
    for field in ("begin", "end"):
        con.execute(
            f'UPDATE raw_artists SET "{field}" = c.value FROM corrections c '
            f"WHERE c.mbid = raw_artists.mbid AND c.field = '{field}'"
        )
    return con.execute("SELECT count(*) FROM corrections").fetchone()[0]


def build(
    con: duckdb.DuckDBPyConnection,
    sql_dir: Path,
    artists: Path,
    rgs: Path,
    corrections: Path | None,
    dump_year: int = 2026,
) -> None:
    load_raw(con, artists, rgs)
    apply_corrections(con, corrections)
    con.execute(f"SET VARIABLE dump_year = {dump_year}")
    for path in sorted(sql_dir.glob("*.sql")):
        if path.name.startswith("90_"):
            continue
        text = path.read_text(encoding="utf-8")
        if path.name == "60_genre_parents.sql":
            if not GENRE_PARENTS_CSV.exists():
                logger.warning(
                    "source genre_parents introuvable (%s) : table publiée vide",
                    GENRE_PARENTS_CSV,
                )
                con.execute(
                    "CREATE OR REPLACE TABLE genre_parents "
                    "(genre_mbid VARCHAR, parent_mbid VARCHAR, source VARCHAR)"
                )
                continue
            text = text.replace(GENRE_PARENTS_LITERAL, GENRE_PARENTS_CSV.as_posix())
        con.execute(text)


INVARIANTS = (
    "duplicate_band", "band_out_of_window", "end_before_begin", "end_after_dump_year",
    "last_album_mismatch", "album_without_band", "album_out_of_window",
    "album_extra_secondary_type",
    "band_without_genre", "band_genres_out_of_order", "unknown_genre",
    "genre_n_bands_mismatch",
    "presence_out_of_range", "presence_end_mismatch",
    "density_out_of_range", "density_above_band_count",
    "genre_parent_unknown_genre", "genre_parent_cycle",
    "corrections_file_too_large", "corrections_invalid",
)


def check_invariants(con: duckdb.DuckDBPyConnection, sql_dir: Path) -> list[tuple[str, int]]:
    con.execute((sql_dir / "90_invariants.sql").read_text(encoding="utf-8"))
    violations = []
    for name in INVARIANTS:
        n = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        if n:
            violations.append((name, n))
    return violations
