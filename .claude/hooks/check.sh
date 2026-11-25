#!/usr/bin/env bash
# Stop hook: Claude cannot finish a turn while `make check` fails.
# Exit 2 sends the tail of the output back to Claude so it fixes the failures and tries again.
# Skips when nothing in src/ or tests/ changed (conversation-only turns stay fast).
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

changed=$(git status --porcelain -- src tests pyproject.toml 2>/dev/null)
ahead=$(git diff --name-only origin/main...HEAD -- src tests 2>/dev/null | head -n 1)
if [ -z "$changed" ] && [ -z "$ahead" ]; then
  exit 0
fi

if ! out=$(make check 2>&1); then
  {
    echo "make check failed. Fix the root cause (do not weaken tests or silence rules):"
    echo "$out" | tail -n 80
  } >&2
  exit 2
fi
exit 0
