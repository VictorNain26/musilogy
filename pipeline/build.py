"""Enchaîne les fichiers SQL de transformation sur une connexion DuckDB."""
from __future__ import annotations

from pathlib import Path

import duckdb

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
        return 0
    con.execute(
        "CREATE OR REPLACE TABLE corrections AS SELECT * FROM read_csv("
        f"'{corrections.as_posix()}', header=true, "
        "columns={mbid:'VARCHAR', champ:'VARCHAR', valeur:'VARCHAR', "
        "justification:'VARCHAR', source:'VARCHAR'})"
    )
    for field in ("begin", "end"):
        con.execute(
            f'UPDATE raw_artists SET "{field}" = c.valeur FROM corrections c '
            f"WHERE c.mbid = raw_artists.mbid AND c.champ = '{field}'"
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
        con.execute(path.read_text(encoding="utf-8"))


INVARIANTS = (
    "duplicate_band", "band_out_of_window", "end_before_begin",
    "last_album_mismatch", "album_without_band", "album_out_of_window",
    "band_without_genre", "band_genres_out_of_order", "unknown_genre",
    "presence_out_of_range", "density_out_of_range", "density_above_band_count",
)


def check_invariants(con: duckdb.DuckDBPyConnection, sql_dir: Path) -> list[tuple[str, int]]:
    con.execute((sql_dir / "90_invariants.sql").read_text(encoding="utf-8"))
    violations = []
    for name in INVARIANTS:
        n = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        if n:
            violations.append((name, n))
    return violations
