#!/usr/bin/env bash
# PostToolUse (Edit|Write): format and auto-fix the Python file that was just edited.
# Never blocks: formatting problems are caught later by check.sh.
set -u
file=$(jq -r '.tool_input.file_path // empty')
case "$file" in
  *.py)
    uv run --quiet ruff format --quiet "$file" >/dev/null 2>&1
    uv run --quiet ruff check --fix --quiet "$file" >/dev/null 2>&1
    ;;
esac
exit 0
