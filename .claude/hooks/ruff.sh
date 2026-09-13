#!/usr/bin/env bash
# Format and lint the Python files that changed, so the session hits the same
# gate as CI (ruff format --check, ruff check) instead of discovering the
# failure at push time.
#
# Wired as a PostToolUse hook with no matcher, so it runs after every tool and
# works out what changed itself. A hook matching Edit|Write would miss most
# edits: in auto mode Claude rewrites files with sed and heredocs through Bash,
# and Claude Code doesn't fire an Edit|Write hook for those.

set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[[ -n "$ROOT" && -d "$ROOT" ]] || exit 0
cd "$ROOT" || exit 0

# Porcelain v1: "XY path", or "R  old -> new" for a rename. The last field is
# the path that exists now. Deleted files drop out on the -f test below.
mapfile -t FILES < <(
    git status --porcelain -- '*.py' 2>/dev/null |
    sed 's/^...//; s/.* -> //' |
    tr -d '"'
)

TARGETS=()
for f in "${FILES[@]}"; do
    [[ -n "$f" && -f "$f" ]] && TARGETS+=("$f")
done
[[ ${#TARGETS[@]} -gt 0 ]] || exit 0

uv run ruff format -q "${TARGETS[@]}" >/dev/null 2>&1
uv run ruff check -q --fix "${TARGETS[@]}" >/dev/null 2>&1

# Whatever --fix could not repair is a real finding: hand it to Claude rather
# than letting it surface in CI.
if ! REMAINING=$(uv run ruff check "${TARGETS[@]}" 2>&1); then
    echo "ruff still reports findings after --fix:" >&2
    echo "$REMAINING" >&2
    exit 2
fi

exit 0
