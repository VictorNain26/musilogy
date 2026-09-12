import gzip
import json
import subprocess

from conftest import build_synthetic, synthetic_artist

from musilogy import REFERENCE_DUMP as DUMP
from musilogy.fetch import expected_sums, sha256_file
from musilogy.paths import PACKAGE_DIR, REFERENCE_DIR
from musilogy.publish import publish

REF_SUMS = REFERENCE_DIR / f"{DUMP}.SHA256SUMS"


def read_web(out_dir, name):
    return json.loads(gzip.decompress((out_dir / "web" / f"{name}.json.gz").read_bytes()))


def test_publish_writes_every_table(con, tmp_path):
    manifest = publish(con, tmp_path, DUMP, None)
    for name in ("bands", "albums", "genres", "genre_parents", "density", "members"):
        assert (tmp_path / f"{name}.parquet").exists()
        assert name in manifest["counts"]
    assert manifest["dump"] == DUMP


def test_members_is_archived_but_stays_out_of_the_web_export(con, tmp_path):
    # The Parquet archive is where the membership table belongs. The web
    # export already weighs 15.6 MB gzip for the timeline alone and layer 1's
    # payload budget is a known open problem: 601k relation rows would make it
    # worse for a consumer that has not asked for them.
    publish(con, tmp_path, DUMP, None)
    assert (tmp_path / "members.parquet").exists()
    assert not (tmp_path / "web" / "members.json.gz").exists()


def test_web_export_is_columnar_and_gzipped(con, tmp_path):
    publish(con, tmp_path, DUMP, None)
    raw = (tmp_path / "web" / "bands_timeline.json.gz").read_bytes()
    assert raw[:2] == b"\x1f\x8b"
    data = json.loads(gzip.decompress(raw))
    assert len(data["name"]) == len(data["y0"])


def test_web_export_carries_what_a_consumer_needs_to_join_and_to_audit(con, tmp_path):
    # The join key and the genres first: without mbid, the 380k timeline rows
    # can be joined to nothing — not to web/genres.json.gz, not to density —
    # and without genres the frieze cannot filter. Then both edges' raw
    # evidence, not just the right one: a derived value is verifiable only if
    # what it derives from travels with it.
    publish(con, tmp_path, DUMP, None)
    data = read_web(tmp_path, "bands_timeline")
    assert set(data) >= {
        "mbid",
        "name",
        "genres",
        "y0",
        "y0_source",
        "y0_declared",
        "y_first_album",
        "y_end",
        "y_end_source",
        "y_end_declared",
        "y_last_album",
        "y_presence_end",
    }
    assert all(data["mbid"])
    assert len(set(data["mbid"])) == len(data["mbid"])

    vocabulary = set(read_web(tmp_path, "genres")["genre_mbid"])
    exported = [g["mbid"] for row in data["genres"] for g in row]
    assert exported, "no band carries a genre: the join is not exercised"
    assert set(exported) <= vocabulary


def test_name_is_not_an_identity_in_the_web_export(con, tmp_path):
    # Three homonym witnesses: keyed by `name`, layer 1 would merge distinct
    # artists. This is why the export carries mbid.
    publish(con, tmp_path, DUMP, None)
    rest = read_web(tmp_path, "bands_rest")
    assert len(set(rest["name"])) < len(rest["name"])
    assert len(set(rest["mbid"])) == len(rest["mbid"])


def test_web_export_is_split_between_timeline_eligible_and_the_rest(con, tmp_path):
    publish(con, tmp_path, DUMP, None)
    timeline = read_web(tmp_path, "bands_timeline")
    rest = read_web(tmp_path, "bands_rest")
    assert all(y0 is not None for y0 in timeline["y0"])
    assert all(y0 is None for y0 in rest["y0"])
    total = con.execute("SELECT count(*) FROM bands").fetchone()[0]
    assert len(timeline["name"]) + len(rest["name"]) == total


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
        "begin_below_min_year": 2,
        "end_below_min_year": 0,
        "end_before_begin": 1,
    }


def test_manifest_carries_the_three_neutralised_inference_counters(con, tmp_path):
    # One counter per guard of 30_bands_lifespan.sql. On the witnesses:
    # Polska Radio One (formed 2015, last album 2014) for the end, Wiener
    # Philharmoniker and Handel and Haydn Society (begins below 1850) for the
    # begin. A neutralised anomaly stays visible instead of being absorbed.
    manifest = publish(con, tmp_path, DUMP, None)
    assert manifest["neutralised_inferences"] == {
        "first_album_after_declared_end": 0,
        "last_album_before_declared_begin": 1,
        "first_album_with_begin_below_min_year": 2,
    }


def test_manifest_carries_git_sha(con, tmp_path):
    manifest = publish(con, tmp_path, DUMP, None)
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=PACKAGE_DIR,
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
    # Deliberately distinct counts per sub-rule: on the shared fixtures,
    # several counters hold the same value, and a key swap (begin_future <->
    # end_future, begin_below_min_year <-> end_below_min_year, for example)
    # would otherwise go unnoticed.
    records = (
        [synthetic_artist(f"begin-illegible-{i}", "????-01-01", None) for i in range(2)]
        + [synthetic_artist(f"end-illegible-{i}", "2000-01-01", "????-06") for i in range(3)]
        + [synthetic_artist(f"begin-future-{i}", "2090-01-01", None) for i in range(4)]
        + [synthetic_artist(f"end-future-{i}", "2000-01-01", "2090-01-01") for i in range(5)]
        + [synthetic_artist(f"end-before-begin-{i}", "2010-01-01", "2005-01-01") for i in range(6)]
        + [synthetic_artist(f"begin-below-min-{i}", "0742", None) for i in range(7)]
        + [synthetic_artist(f"end-below-min-{i}", None, "1700-01-01") for i in range(8)]
    )
    c = build_synthetic(tmp_path, records)
    manifest = publish(c, tmp_path / "out", DUMP, None)

    assert manifest["r2_anomalies"] == {
        "begin_illegible": 2,
        "end_illegible": 3,
        "begin_future": 4,
        "end_future": 5,
        "begin_below_min_year": 7,
        "end_below_min_year": 8,
        "end_before_begin": 6,
    }


def test_parquet_archives_are_zstd_compressed(con, tmp_path):
    publish(con, tmp_path, DUMP, None)
    parquet_path = (tmp_path / "bands.parquet").as_posix()
    codecs = con.execute(
        f"SELECT DISTINCT compression FROM parquet_metadata('{parquet_path}')"
    ).fetchall()
    assert codecs == [("ZSTD",)]
