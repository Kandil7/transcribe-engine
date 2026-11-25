#!/usr/bin/env bash
# Autopilot runner: one fresh Claude Code session per slice, until the build is done or blocked.
#
# Each iteration runs prompts/AUTOPILOT.md headless (`claude -p`), so every slice starts with a clean
# context; progress lives in git and .autopilot/state.json, not in the conversation.
#
# Usage:  scripts/autopilot.sh            # run until done/blocked (max 40 iterations)
#         MAX_ITER=5 scripts/autopilot.sh # cap iterations
# Env:
#   MODE=auto              permission mode: auto (default, classifier-reviewed) | acceptEdits
#   MAX_ITER=40            iteration cap
#   ITER_TIMEOUT=14400     seconds per iteration (needs `timeout` or `gtimeout`)
#   BUDGET_PER_RUN=        optional USD cap per iteration (--max-budget-usd)
#   MAX_STALLS=3           stop after N iterations with no change to main or state
set -uo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE=.autopilot/state.json
LOGDIR=.autopilot/logs
PROMPT=prompts/AUTOPILOT.md
MODE=${MODE:-auto}
MAX_ITER=${MAX_ITER:-40}
ITER_TIMEOUT=${ITER_TIMEOUT:-14400}
MAX_STALLS=${MAX_STALLS:-3}
mkdir -p "$LOGDIR"

for bin in claude jq git; do
  command -v "$bin" >/dev/null || { echo "autopilot: '$bin' not found" >&2; exit 1; }
done
[ -f "$PROMPT" ] || { echo "autopilot: $PROMPT missing" >&2; exit 1; }
if [ "$MODE" = "bypassPermissions" ]; then
  echo "autopilot: bypassPermissions is not allowed here; use MODE=auto" >&2; exit 1
fi

TIMEOUT_BIN=$(command -v timeout || command -v gtimeout || true)
EXTRA=()
if claude --help 2>/dev/null | grep -q -- '--permission-prompts'; then
  EXTRA+=(--permission-prompts none)
fi
[ -n "${BUDGET_PER_RUN:-}" ] && EXTRA+=(--max-budget-usd "$BUDGET_PER_RUN")

HASH_BIN=$(command -v shasum || command -v sha1sum)
fingerprint() {
  { git rev-parse main 2>/dev/null; git rev-parse HEAD 2>/dev/null; cat "$STATE" 2>/dev/null; } | "$HASH_BIN" | cut -c1-12
}
status() { jq -r '.status // "not_started"' "$STATE" 2>/dev/null || echo "not_started"; }

stalls=0
for ((i = 1; i <= MAX_ITER; i++)); do
  st=$(status)
  if [ "$st" = "done" ] || [ "$st" = "blocked" ]; then
    echo "autopilot: status=$st — stopping."
    break
  fi

  ts=$(date +%Y%m%d-%H%M%S)
  log="$LOGDIR/$ts-iter$i.json"
  before=$(fingerprint)
  echo "autopilot: iteration $i/$MAX_ITER (status=$st, current=$(jq -r '.current // "-"' "$STATE" 2>/dev/null)) → $log"

  cmd=(claude -p "$(cat "$PROMPT")" --permission-mode "$MODE" --output-format json "${EXTRA[@]}")
  if [ -n "$TIMEOUT_BIN" ]; then
    "$TIMEOUT_BIN" --signal=INT "$ITER_TIMEOUT" "${cmd[@]}" >"$log" 2>"$log.err"
  else
    "${cmd[@]}" >"$log" 2>"$log.err"
  fi
  rc=$?

  after=$(fingerprint)
  cost=$(jq -r '.total_cost_usd // empty' "$log" 2>/dev/null)
  summary=$(jq -r '.result // empty' "$log" 2>/dev/null | tail -n 5)
  printf '%s\titer=%d\trc=%d\tstatus=%s\tcurrent=%s\tcost=%s\n' \
    "$ts" "$i" "$rc" "$(status)" "$(jq -r '.current // "-"' "$STATE" 2>/dev/null)" "${cost:-?}" \
    >>"$LOGDIR/runs.tsv"
  [ -n "$summary" ] && echo "$summary"

  if [ "$before" = "$after" ]; then
    stalls=$((stalls + 1))
    echo "autopilot: no progress this iteration ($stalls/$MAX_STALLS), rc=$rc"
    if [ "$stalls" -ge "$MAX_STALLS" ]; then
      echo "autopilot: stalled — see $LOGDIR and docs/REVIEW_QUEUE.md" >&2
      exit 2
    fi
  else
    stalls=0
  fi
done

echo "autopilot: finished with status=$(status). Read docs/PROGRESS.md and docs/BUILD_LOG.md."
