#!/usr/bin/env bash
# Format and lint a Python file right after Claude edits it, so the session
# hits the same gate as CI (ruff format --check, ruff check) instead of
# discovering the failure at push time.
#
# Wired as a PostToolUse hook filtered by `if: Edit(**/*.py)`, so the path
# check here only guards against a file outside the package.

set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[[ -n "$ROOT" ]] || exit 0

FILE=$(jq -r '.tool_input.file_path // ""' 2>/dev/null) || exit 0
[[ -n "$FILE" && -f "$FILE" && "$FILE" == *.py ]] || exit 0
[[ "$FILE" == "$ROOT"/* ]] || exit 0

cd "$ROOT" || exit 0

uv run ruff format -q "$FILE" >/dev/null 2>&1
uv run ruff check -q --fix "$FILE" >/dev/null 2>&1

# Whatever --fix could not repair is a real finding: hand it to Claude rather
# than letting it surface in CI.
if ! REMAINING=$(uv run ruff check "$FILE" 2>&1); then
    echo "ruff still reports findings in ${FILE#"$ROOT"/} after --fix:" >&2
    echo "$REMAINING" >&2
    exit 2
fi

exit 0
