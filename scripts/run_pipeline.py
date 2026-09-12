"""Exécution complète sur les extractions de la Task 3."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb  # noqa: E402

from pipeline.build import build, check_invariants  # noqa: E402
from pipeline.publish import publish  # noqa: E402

DUMP = "20260909-001002"
con = duckdb.connect(":memory:")
build(con, Path("pipeline/sql"), Path("data/work/artists.jsonl"),
      Path("data/work/release_groups.jsonl"), Path("pipeline/corrections.csv"))

violations = check_invariants(con, Path("pipeline/sql"))
if violations:
    raise SystemExit(f"invariants violés : {violations}")

manifest = publish(con, Path("data/out") / DUMP, DUMP, Path("pipeline/corrections.csv"))
print(manifest["counts"])
