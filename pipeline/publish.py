"""Écrit les livrables : Parquet d'archive, JSON colonnaire pour le web, manifeste."""
from __future__ import annotations

import gzip
import json
import subprocess
from pathlib import Path

import duckdb

from pipeline.fetch import expected_sums, sha256_file

TABLES = ("bands", "albums", "genres", "genre_parents", "density")
WEB_COLUMNS = {
    "bands": ["name", "y0", "y_end_declared", "y_last_album", "y_presence_end",
              "ended", "country", "begin_area"],
    "genres": ["genre_mbid", "name", "n_bands"],
}
REFERENCE_DIR = Path("pipeline/reference")
R2_ANOMALY_QUERY = """
    SELECT
      sum(CASE WHEN begin IS NOT NULL AND yr(begin) IS NULL THEN 1 ELSE 0 END),
      sum(CASE WHEN "end" IS NOT NULL AND yr("end") IS NULL THEN 1 ELSE 0 END),
      sum(CASE WHEN yr(begin) IS NOT NULL
                AND yr(begin) > getvariable('dump_year') THEN 1 ELSE 0 END),
      sum(CASE WHEN yr("end") IS NOT NULL
                AND yr("end") > getvariable('dump_year') THEN 1 ELSE 0 END),
      sum(CASE WHEN yr(begin) IS NOT NULL AND yr("end") IS NOT NULL
                AND yr("end") <= getvariable('dump_year')
                AND yr("end") < yr(begin) THEN 1 ELSE 0 END)
    FROM raw_artists
"""
R2_ANOMALY_KEYS = (
    "begin_illegible", "end_illegible", "begin_future", "end_future", "end_before_begin",
)


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def _columnar(con: duckdb.DuckDBPyConnection, table: str, columns: list[str]) -> dict:
    rows = con.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
    return {c: [r[i] for r in rows] for i, c in enumerate(columns)}


def _r2_anomalies(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    row = con.execute(R2_ANOMALY_QUERY).fetchone()
    return {key: int(value) for key, value in zip(R2_ANOMALY_KEYS, row)}


def publish(
    con: duckdb.DuckDBPyConnection,
    out_dir: Path,
    dump: str,
    corrections: Path | None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "web").mkdir(exist_ok=True)

    counts = {}
    for name in TABLES:
        con.execute(
            f"COPY {name} TO '{(out_dir / f'{name}.parquet').as_posix()}' "
            "(FORMAT parquet, COMPRESSION zstd)"
        )
        counts[name] = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]

    for table, columns in WEB_COLUMNS.items():
        payload = json.dumps(
            _columnar(con, table, columns), ensure_ascii=False, separators=(",", ":")
        ).encode()
        (out_dir / "web" / f"{table}.json.gz").write_bytes(gzip.compress(payload, 9))

    manifest = {
        "dump": dump,
        "archive_sha256": expected_sums(REFERENCE_DIR / f"{dump}.SHA256SUMS"),
        "counts": counts,
        "r2_anomalies": _r2_anomalies(con),
        "git_sha": _git_sha(),
        "corrections_sha256": sha256_file(corrections) if corrections else None,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return manifest
