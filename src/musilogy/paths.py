"""Chemins ancrés sur le paquet, jamais sur le cwd de l'appelant."""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SQL_DIR = PACKAGE_DIR / "sql"
REFERENCE_DIR = PACKAGE_DIR / "reference"
CORRECTIONS_CSV = PACKAGE_DIR / "corrections.csv"

REPO_ROOT = PACKAGE_DIR.parents[1]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def work_dir(dump: str) -> Path:
    """Une extraction porte le dump dont elle provient. Sans ce niveau, un
    `musilogy run` lancé après un bump de REFERENCE_DUMP reconstruit sur
    l'extraction précédente et publie un manifeste qui nomme le nouveau dump
    et ses empreintes — la sortie affirme alors une source qu'elle n'a pas lue."""
    return DATA_DIR / "work" / dump


def out_dir(dump: str) -> Path:
    return DATA_DIR / "out" / dump
