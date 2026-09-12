import gzip
import json
import subprocess
from pathlib import Path
import duckdb
import pytest
from pipeline import REFERENCE_DUMP as DUMP
from pipeline.build import build
from pipeline.fetch import expected_sums, sha256_file
from pipeline.publish import publish

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")
REF_SUMS = Path("pipeline/reference") / f"{DUMP}.SHA256SUMS"


def _synthetic_artist(mbid: str, begin: str | None, end: str | None) -> dict:
    return {
        "mbid": mbid, "name": mbid, "type": "Group",
        "begin": begin, "end": end, "ended": False,
        "country": None, "area": None, "begin_area": None,
        "genres": [], "members": [],
    }


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    build(c, SQL, FIX / "artists.jsonl", FIX / "release_groups.jsonl", None)
    return c


def test_publish_writes_every_table(con, tmp_path):
    manifest = publish(con, tmp_path, DUMP, None)
    for name in ("bands", "albums", "genres", "genre_parents", "density"):
        assert (tmp_path / f"{name}.parquet").exists()
        assert name in manifest["counts"]
    assert manifest["dump"] == DUMP


def test_web_export_is_columnar_and_gzipped(con, tmp_path):
    publish(con, tmp_path, DUMP, None)
    raw = (tmp_path / "web" / "bands.json.gz").read_bytes()
    assert raw[:2] == b"\x1f\x8b"
    data = json.loads(gzip.decompress(raw))
    assert set(data) >= {"name", "y0", "y_end_declared", "y_last_album", "y_presence_end"}
    assert len(data["name"]) == len(data["y0"])


def test_presence_is_never_published(con, tmp_path):
    manifest = publish(con, tmp_path, DUMP, None)
    assert "presence" not in manifest["counts"]
    assert not (tmp_path / "presence.parquet").exists()
    assert not (tmp_path / "web" / "presence.json.gz").exists()


def test_manifest_carries_archive_checksums(con, tmp_path):
    manifest = publish(con, tmp_path, DUMP, None)
    assert manifest["archive_sha256"] == expected_sums(REF_SUMS)


def test_manifest_carries_r2_anomaly_counters(con, tmp_path):
    manifest = publish(con, tmp_path, DUMP, None)
    assert manifest["r2_anomalies"] == {
        "begin_illegible": 1,
        "end_illegible": 1,
        "begin_future": 1,
        "end_future": 1,
        "end_before_begin": 1,
    }


def test_manifest_carries_git_sha(con, tmp_path):
    manifest = publish(con, tmp_path, DUMP, None)
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert manifest["git_sha"] == expected


def test_manifest_carries_corrections_checksum_when_present(con, tmp_path):
    corrections = tmp_path / "corrections.csv"
    corrections.write_text("mbid,field,value,justification,source\n", encoding="utf-8")
    manifest = publish(con, tmp_path, DUMP, corrections)
    assert manifest["corrections_sha256"] == sha256_file(corrections)


def test_manifest_corrections_checksum_is_none_without_file(con, tmp_path):
    manifest = publish(con, tmp_path, DUMP, None)
    assert manifest["corrections_sha256"] is None


def test_r2_anomaly_counters_are_not_mismapped_between_subrules(tmp_path):
    # Comptes volontairement distincts par sous-règle : sur les fixtures
    # partagées, les cinq compteurs valent tous 1 et un échange de clés
    # (begin_future <-> end_future, par exemple) resterait invisible.
    records = (
        [_synthetic_artist(f"begin-illegible-{i}", "????-01-01", None) for i in range(2)]
        + [_synthetic_artist(f"end-illegible-{i}", "2000-01-01", "????-06") for i in range(3)]
        + [_synthetic_artist(f"begin-future-{i}", "2090-01-01", None) for i in range(4)]
        + [_synthetic_artist(f"end-future-{i}", "2000-01-01", "2090-01-01") for i in range(5)]
        + [_synthetic_artist(f"end-before-begin-{i}", "2010-01-01", "2005-01-01") for i in range(6)]
    )
    artists = tmp_path / "synthetic_artists.jsonl"
    artists.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    release_groups = tmp_path / "synthetic_release_groups.jsonl"
    release_groups.write_text("", encoding="utf-8")

    c = duckdb.connect(":memory:")
    build(c, SQL, artists, release_groups, None)
    out = tmp_path / "out"
    manifest = publish(c, out, DUMP, None)

    assert manifest["r2_anomalies"] == {
        "begin_illegible": 2,
        "end_illegible": 3,
        "begin_future": 4,
        "end_future": 5,
        "end_before_begin": 6,
    }


def test_parquet_archives_are_zstd_compressed(con, tmp_path):
    publish(con, tmp_path, DUMP, None)
    codecs = con.execute(
        f"SELECT DISTINCT compression FROM parquet_metadata('{(tmp_path / 'bands.parquet').as_posix()}')"
    ).fetchall()
    assert codecs == [("ZSTD",)]
