import gzip
import json
import subprocess
from pathlib import Path
import duckdb
import pytest
from pipeline.build import build
from pipeline.fetch import expected_sums, sha256_file
from pipeline.publish import publish

FIX = Path("pipeline/tests/fixtures")
SQL = Path("pipeline/sql")
DUMP = "20260909-001002"
REF_SUMS = Path("pipeline/reference") / f"{DUMP}.SHA256SUMS"


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
    corrections.write_text("mbid,champ,valeur,justification,source\n", encoding="utf-8")
    manifest = publish(con, tmp_path, DUMP, corrections)
    assert manifest["corrections_sha256"] == sha256_file(corrections)


def test_manifest_corrections_checksum_is_none_without_file(con, tmp_path):
    manifest = publish(con, tmp_path, DUMP, None)
    assert manifest["corrections_sha256"] is None
