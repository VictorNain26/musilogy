"""Écrit les livrables : Parquet d'archive, JSON colonnaire pour le web, manifeste."""

from __future__ import annotations

import gzip
import json
import subprocess
from pathlib import Path
from typing import Any

import duckdb

from musilogy.fetch import expected_sums, sha256_file
from musilogy.paths import PACKAGE_DIR, REFERENCE_DIR

TABLES = ("bands", "albums", "genres", "density", "members")
BANDS_WEB_COLUMNS = [
    # mbid first: it is the only key layer 1 can join on — against
    # web/genres.json.gz, against density, against anything. `name` is not an
    # identity, the witnesses alone carry three homonyms.
    "mbid",
    "name",
    "type",
    # Both edges travel with their raw evidence, not just the right one: a
    # derived value is verifiable only if what it derives from is exported too.
    "y0",
    "y0_source",
    "y0_declared",
    "y_first_album",
    "y_end",
    "y_end_source",
    "y_end_declared",
    "y_last_album",
    "y_presence_end",
    "ended",
    "country",
    "begin_area",
    "genres",
]
WEB_COLUMNS = {
    # The two reliability columns are not decoration: without them a web-only
    # consumer cannot apply the exclusion rule of 60_density.sql, recomputes
    # density from bands_timeline alone, and silently invents the 828 cells of
    # the art-music genres this layer deliberately withholds.
    "genres": ["genre_mbid", "name", "n_bands", "n_candidate_albums", "multi_artist_drop_pct"],
    # Published too, so the frieze reads the aggregate rather than rebuilding
    # it: a consumer that recomputes it reimplements a rule, and reimplementing
    # is where the exclusion gets lost.
    "density": ["genre_mbid", "year", "present"],
}


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=PACKAGE_DIR,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _columnar(con: duckdb.DuckDBPyConnection, table: str, columns: list[str]) -> dict[str, Any]:
    rows = con.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
    return {c: [r[i] for r in rows] for i, c in enumerate(columns)}


def _counters(con: duckdb.DuckDBPyConnection, table: str) -> dict[str, int]:
    """Counter table -> manifest entry. Read by column name, never by position:
    a counter added to the SQL surfaces without touching this function."""
    result = con.execute(f"SELECT * FROM {table}")
    assert result.description is not None
    names = [c[0] for c in result.description]
    row = result.fetchone()
    assert row is not None  # counter tables are single-row aggregates
    return {name: int(value) for name, value in zip(names, row, strict=True)}


def publish(
    con: duckdb.DuckDBPyConnection,
    out_dir: Path,
    dump: str,
    corrections: Path | None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    web_dir = out_dir / "web"
    web_dir.mkdir(exist_ok=True)
    written: set[str] = set()

    counts: dict[str, int] = {}
    for name in TABLES:
        con.execute(
            f"COPY {name} TO ? (FORMAT parquet, COMPRESSION zstd)",
            [(out_dir / f"{name}.parquet").as_posix()],
        )
        row = con.execute(f"SELECT count(*) FROM {name}").fetchone()
        assert row is not None  # COUNT(*) always returns exactly one row
        counts[name] = int(row[0])

    for table, columns in WEB_COLUMNS.items():
        payload = json.dumps(
            _columnar(con, table, columns), ensure_ascii=False, separators=(",", ":")
        ).encode()
        (web_dir / f"{table}.json.gz").write_bytes(gzip.compress(payload, 9))
        written.add(f"{table}.json.gz")

    # Split in two: layer 1's frieze only needs the timeline-eligible bands
    # (y0 IS NOT NULL); pulling in the rest would double the payload for no
    # benefit to that consumer.
    for name, condition in (
        ("bands_timeline", "y0 IS NOT NULL"),
        ("bands_rest", "y0 IS NULL"),
    ):
        columns_sql = ", ".join(BANDS_WEB_COLUMNS)
        rows = con.execute(f"SELECT {columns_sql} FROM bands WHERE {condition}").fetchall()
        payload = json.dumps(
            {c: [r[i] for r in rows] for i, c in enumerate(BANDS_WEB_COLUMNS)},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        (web_dir / f"{name}.json.gz").write_bytes(gzip.compress(payload, 9))
        written.add(f"{name}.json.gz")

    # Prune what this run did not write. Without it an export dropped from a
    # previous schema survives in the delivered directory: a consumer globbing
    # web/*.json.gz then loads a file describing a population that no longer
    # exists, joinable to nothing.
    for stale in web_dir.glob("*.json.gz"):
        if stale.name not in written:
            stale.unlink()

    manifest = {
        "dump": dump,
        "archive_sha256": expected_sums(REFERENCE_DIR / f"{dump}.SHA256SUMS"),
        "counts": counts,
        "r2_anomalies": _counters(con, "r2_anomalies"),
        "neutralised_inferences": _counters(con, "neutralised_inferences"),
        "density_exclusions": _counters(con, "density_exclusions"),
        "git_sha": _git_sha(),
        "corrections_sha256": sha256_file(corrections) if corrections else None,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return manifest
