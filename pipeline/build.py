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


def build(
    con: duckdb.DuckDBPyConnection,
    sql_dir: Path,
    artists: Path,
    rgs: Path,
    corrections: Path | None,
    dump_year: int = 2026,
) -> None:
    load_raw(con, artists, rgs)
    con.execute(f"SET VARIABLE dump_year = {dump_year}")
    for path in sorted(sql_dir.glob("*.sql")):
        if path.name.startswith("90_"):
            continue
        con.execute(path.read_text(encoding="utf-8"))
