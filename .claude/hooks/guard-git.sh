#!/usr/bin/env bash
# PreToolUse (Bash): block dangerous git operations.
#  - commits on main
#  - force push (plain --force / -f); --force-with-lease on a feature branch is allowed
#  - pushes to main
#  - skipping hooks with --no-verify
set -u
cmd=$(jq -r '.tool_input.command // empty')
[ -z "$cmd" ] && exit 0

case "$cmd" in
  *git*) ;;
  *) exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || true
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

if echo "$cmd" | grep -Eq 'git[[:space:]]+commit' && [ "$branch" = "main" ]; then
  echo "Blocked: do not commit on main. Create a slice branch: git switch -c feat/SXX-<slug>" >&2
  exit 2
fi

if echo "$cmd" | grep -Eq -- '--no-verify'; then
  echo "Blocked: --no-verify skips the checks. Fix the failing check instead." >&2
  exit 2
fi

if echo "$cmd" | grep -Eq 'git[[:space:]]+push'; then
  if echo "$cmd" | grep -Eq -- '(^|[[:space:]])(--force|-f)([[:space:]]|$)'; then
    echo "Blocked: plain force push. Use --force-with-lease on your own feature branch." >&2
    exit 2
  fi
  if echo "$cmd" | grep -Eq '(origin[[:space:]]+main|:main)([[:space:]]|$)'; then
    echo "Blocked: never push to main. Open a PR." >&2
    exit 2
  fi
fi
exit 0
