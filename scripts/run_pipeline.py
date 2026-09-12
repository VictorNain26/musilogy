"""Exécution complète : fetch → extract (si besoin) → transform → validate → publish."""
from pathlib import Path

import duckdb

from pipeline import REFERENCE_DUMP as DUMP
from pipeline.build import build, check_invariants
from pipeline.extract import extract, reduce_artist, reduce_release_group
from pipeline.fetch import fetch_dump
from pipeline.publish import publish

RAW_DIR = Path("data/raw")
WORK_DIR = Path("data/work")
SUMS_PATH = Path("pipeline/reference") / f"{DUMP}.SHA256SUMS"
ARTISTS_JSONL = WORK_DIR / "artists.jsonl"
RELEASE_GROUPS_JSONL = WORK_DIR / "release_groups.jsonl"


def fetch_and_extract() -> None:
    """§5.1 fetch → extract. Rejouable : fetch_dump ne retélécharge pas une
    archive déjà vérifiée, extract réécrit sa sortie à chaque appel."""
    artist_archive = fetch_dump(DUMP, "artist.tar.xz", RAW_DIR, SUMS_PATH)
    rg_archive = fetch_dump(DUMP, "release-group.tar.xz", RAW_DIR, SUMS_PATH)
    extract(artist_archive, reduce_artist, ARTISTS_JSONL)
    extract(rg_archive, reduce_release_group, RELEASE_GROUPS_JSONL)


if not ARTISTS_JSONL.exists() or not RELEASE_GROUPS_JSONL.exists():
    fetch_and_extract()

con = duckdb.connect(":memory:")
build(con, Path("pipeline/sql"), ARTISTS_JSONL, RELEASE_GROUPS_JSONL,
      Path("pipeline/corrections.csv"))

violations = check_invariants(con, Path("pipeline/sql"))
if violations:
    raise SystemExit(f"invariants violated: {violations}")

manifest = publish(con, Path("data/out") / DUMP, DUMP, Path("pipeline/corrections.csv"))
print(manifest["counts"])
