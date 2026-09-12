"""Projection en flux des dumps JSON MusicBrainz. Aucune règle métier ici."""
from __future__ import annotations

import json
import logging
import lzma
import tarfile
from pathlib import Path
from typing import Callable, Iterator

logger = logging.getLogger(__name__)

KEPT_TYPES = {"Group", "Orchestra", "Choir"}


def reduce_artist(rec: dict) -> dict | None:
    if rec.get("type") not in KEPT_TYPES:
        return None
    span = rec.get("life-span") or {}
    return {
        "mbid": rec.get("id"),
        "name": rec.get("name"),
        "type": rec.get("type"),
        "begin": span.get("begin"),
        "end": span.get("end"),
        "ended": span.get("ended"),
        "country": rec.get("country"),
        "area": (rec.get("area") or {}).get("name"),
        "begin_area": (rec.get("begin-area") or {}).get("name"),
        "genres": [
            {"mbid": g.get("id"), "name": g.get("name"), "votes": g.get("count", 0)}
            for g in (rec.get("genres") or [])
        ],
        "members": [
            {
                "mbid": (r.get("artist") or {}).get("id"),
                "begin": r.get("begin"),
                "end": r.get("end"),
            }
            for r in (rec.get("relations") or [])
            if r.get("type") == "member of band"
        ],
    }


def reduce_release_group(rec: dict) -> dict | None:
    if rec.get("primary-type") != "Album":
        return None
    return {
        "mbid": rec.get("id"),
        "title": rec.get("title"),
        "date": rec.get("first-release-date"),
        "secondary": rec.get("secondary-types") or [],
        "artists": [
            (c.get("artist") or {}).get("id") for c in (rec.get("artist-credit") or [])
        ],
    }


def iter_records(archive: Path) -> Iterator[dict]:
    """Parcourt les lignes JSON de mbdump/* sans jamais écrire le tar décompressé."""
    skipped = 0
    with lzma.open(archive) as xz, tarfile.open(fileobj=xz, mode="r|") as tar:
        for member in tar:
            if not member.isfile() or not member.name.startswith("mbdump/"):
                continue
            stream = tar.extractfile(member)
            if stream is None:
                continue
            for raw in stream:
                line = raw.strip()
                if not line.startswith(b"{"):
                    continue
                try:
                    yield json.loads(line, strict=False)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
    if skipped:
        logger.warning("%s : %d ligne(s) JSON malformée(s) ignorée(s)", archive, skipped)


def extract(archive: Path, reducer: Callable[[dict], dict | None], out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    with open(out, "w", encoding="utf-8") as fh:
        for rec in iter_records(archive):
            reduced = reducer(rec)
            if reduced is None:
                continue
            fh.write(json.dumps(reduced, ensure_ascii=False) + "\n")
            kept += 1
    return kept
