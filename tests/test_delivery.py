import hashlib
import json
import subprocess

from musilogy.paths import REPO_ROOT, WEB_DATA_DIR


def test_the_versioned_blobs_match_the_manifest_they_shipped_with():
    # The blobs are versioned but data/out/ is not, so nothing else can catch a
    # hand-edited or half-copied file: the manifest travels with them and the
    # fast suite is the only place the two are ever compared. Walking the
    # directory rather than a hardcoded list also catches a file sync_web
    # forgot to prune.
    manifest = json.loads((WEB_DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    digests = manifest["output_sha256"]
    for path in sorted(WEB_DATA_DIR.iterdir()):
        if not path.is_file() or path.name == "manifest.json":
            continue
        key = f"web/{path.name}"
        assert key in digests, f"{path.name} has no manifest entry: run `musilogy sync-web`"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == digests[key], (
            f"{path.name} does not match the manifest: run `musilogy sync-web`"
        )


def test_the_versioned_blobs_are_not_ignored_by_git():
    for path in sorted(WEB_DATA_DIR.iterdir()):
        if not path.is_file():
            continue
        rel = f"web/public/data/{path.name}"
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", rel],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 128, (
            f"git check-ignore could not answer for {rel}: {result.stderr.strip()}"
        )
        assert result.returncode == 1, f"{rel} is ignored: {result.stdout.strip()}"
