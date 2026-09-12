"""Exécution complète sur les extractions de la Task 3."""
from pathlib import Path

import duckdb

from pipeline.build import build, check_invariants
from pipeline.publish import publish

DUMP = "20260909-001002"
con = duckdb.connect(":memory:")
build(con, Path("pipeline/sql"), Path("data/work/artists.jsonl"),
      Path("data/work/release_groups.jsonl"), Path("pipeline/corrections.csv"))

violations = check_invariants(con, Path("pipeline/sql"))
if violations:
    raise SystemExit(f"invariants violés : {violations}")

manifest = publish(con, Path("data/out") / DUMP, DUMP, Path("pipeline/corrections.csv"))
print(manifest["counts"])
