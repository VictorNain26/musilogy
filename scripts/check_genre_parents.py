"""Vérifie l'archive Wikidata contre son empreinte. Aucun appel réseau."""
from pathlib import Path

from pipeline.fetch import sha256_file

csv = Path("pipeline/reference/20260912-wikidata-genre-parents.csv")
expected = Path(str(csv) + ".sha256").read_text(encoding="utf-8").split()[0]
actual = sha256_file(csv)
assert actual == expected, f"archive alteree : {actual} != {expected}"
print(csv, sum(1 for _ in open(csv, encoding="utf-8")), "lignes")
