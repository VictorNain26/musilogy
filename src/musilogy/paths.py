"""Chemins ancrés sur le paquet, jamais sur le cwd de l'appelant."""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SQL_DIR = PACKAGE_DIR / "sql"
REFERENCE_DIR = PACKAGE_DIR / "reference"
CORRECTIONS_CSV = PACKAGE_DIR / "corrections.csv"
