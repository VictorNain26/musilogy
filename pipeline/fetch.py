"""Téléchargement et vérification des archives MusicBrainz."""
from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from pathlib import Path

UA = "musilogy/0.1 ( victor.lenain26@gmail.com )"
BASE = "https://data.metabrainz.org/pub/musicbrainz/data/json-dumps"
DOWNLOAD_TIMEOUT = 30.0  # secondes, par connexion (connect + chaque read)


class ChecksumError(Exception):
    pass


class DownloadError(Exception):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_sums(sums_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        out[name.strip().lstrip("*")] = digest
    return out


def verify(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise ChecksumError(f"{path.name}: attendu {expected}, obtenu {actual}")


def download(url: str, dest: Path, timeout: float = DOWNLOAD_TIMEOUT) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as out:
            while chunk := r.read(1 << 20):
                out.write(chunk)
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        raise DownloadError(f"échec du téléchargement de {url} : {e}") from e
    return dest


def fetch_dump(date: str, name: str, raw_dir: Path, sums_path: Path) -> Path:
    dest = raw_dir / date / name
    if not dest.exists():
        download(f"{BASE}/{date}/{name}", dest)
    verify(dest, expected_sums(sums_path)[name])
    return dest
