import hashlib
import json
import subprocess

from musilogy.paths import REPO_ROOT, WEB_DATA_DIR

DELIVERED = (
    "frieze.bin.gz",
    "lineage.bin.gz",
    "frieze_ids.bin",
    "genres.json.gz",
    "density.json.gz",
)


def test_the_versioned_blobs_match_the_manifest_they_shipped_with():
    # The blobs are versioned but data/out/ is not, so nothing else can catch a
    # hand-edited or half-copied file: the manifest travels with them and the
    # fast suite is the only place the two are ever compared.
    manifest = json.loads((WEB_DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    digests = manifest["output_sha256"]
    for name in DELIVERED:
        expected = digests[f"web/{name}"]
        actual = hashlib.sha256((WEB_DATA_DIR / name).read_bytes()).hexdigest()
        assert actual == expected, f"{name} does not match the manifest: run `musilogy sync-web`"


def test_the_versioned_blobs_are_not_ignored_by_git():
    for name in (*DELIVERED, "manifest.json"):
        path = f"web/public/data/{name}"
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 128, (
            f"git check-ignore could not answer for {path}: {result.stderr.strip()}"
        )
        assert result.returncode == 1, f"{path} is ignored: {result.stdout.strip()}"
