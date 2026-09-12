import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from musilogy.build import build
from musilogy.paths import SQL_DIR

FIX = Path(__file__).parent / "fixtures"
SQL = SQL_DIR


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


# Synthetic records, for the date shapes the witnesses do not carry (a begin
# below the floor, an end in 1537...). They validate a rule against a shape,
# never the source itself: anything a real witness can show is tested on the
# fixtures instead.
def synthetic_artist(
    mbid: str,
    begin: str | None,
    end: str | None,
    members: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "mbid": mbid,
        "name": mbid,
        "type": "Group",
        "begin": begin,
        "end": end,
        "ended": end is not None,
        "country": None,
        "begin_area": None,
        "genres": [],
        "members": members or [],
    }


def synthetic_release_group(
    mbid: str, artist: str, date: str, secondary: list[str] | None = None
) -> dict[str, Any]:
    return {
        "mbid": mbid,
        "title": mbid,
        "date": date,
        "secondary": secondary or [],
        "artists": [artist],
    }


def build_synthetic(tmp_path, artists, release_groups=()):
    artists_path = tmp_path / "artists.jsonl"
    rgs_path = tmp_path / "release_groups.jsonl"
    artists_path.write_text("".join(json.dumps(a) + "\n" for a in artists), encoding="utf-8")
    rgs_path.write_text("".join(json.dumps(r) + "\n" for r in release_groups), encoding="utf-8")
    c = duckdb.connect(":memory:")
    build(c, SQL, artists_path, rgs_path, None)
    return c
