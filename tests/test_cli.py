import pytest

from musilogy.cli import _stop_on_extraction_mismatch


def manifest(match):
    return {
        "inputs": {
            "rows_loaded": {"raw_artists": 682447, "raw_release_groups": 2317879},
            "extraction": {"artists_kept": 682447, "release_groups_kept": 2317879},
            "extraction_matches_rows_loaded": match,
        }
    }


def test_a_mismatch_stops_the_run():
    # publish() measured the discrepancy and published it, but nothing acted on
    # it: a truncated extraction — a full disk mid-write — makes the build
    # silently smaller and the run publishes a dataset that presents itself as
    # complete. Removing the guard, or moving the comparison out of the run
    # path, makes this test fail.
    with pytest.raises(SystemExit) as raised:
        _stop_on_extraction_mismatch(manifest(False))
    assert "extraction mismatch" in str(raised.value)


def test_no_extraction_record_is_not_a_mismatch():
    # None means the sidecar is absent, unreadable, or missing a count: it says
    # nothing about the extraction. A truthiness test instead of `is False`
    # would read that silence as a failure and stop every run built on a
    # pre-sidecar extraction — the reference dump's own case today.
    _stop_on_extraction_mismatch(manifest(None))


def test_counts_that_agree_let_the_run_through():
    _stop_on_extraction_mismatch(manifest(True))
