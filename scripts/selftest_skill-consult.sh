#!/usr/bin/env bash
# selftest_skill-consult.sh — regression probe for scripts/skill-consult-check.sh
#
# Asserts:
#   (a) An Agent spawn whose description matches a known skill triggers a stderr
#       nudge and exits 0.
#   (b) An Agent spawn whose description matches nothing emits no nudge and exits 0.
#   (c) A non-Agent tool call (e.g. Bash) is always silent and exits 0.
#
# Usage: bash scripts/selftest_skill-consult.sh
# Run from the repository root or any directory; paths are resolved relative to
# this script's own location.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/skill-consult-check.sh"

if [[ ! -f "$SCRIPT" ]]; then
  printf 'selftest: ERROR: script not found: %s\n' "$SCRIPT" >&2
  exit 1
fi

failures=0

# ── Helper ───────────────────────────────────────────────────────────────────
# run_hook <json> → sets HOOK_STDOUT, HOOK_STDERR, HOOK_EXIT
run_hook() {
  local json="$1"
  HOOK_STDOUT=""
  HOOK_STDERR=""
  HOOK_EXIT=0
  HOOK_STDERR="$(printf '%s' "$json" | bash "$SCRIPT" 2>&1 1>/dev/null)" || HOOK_EXIT=$?
  HOOK_STDOUT="$(printf '%s' "$json" | bash "$SCRIPT" 2>/dev/null)" || true
}

# ── Case (a): matching description → nudge on stderr, exit 0 ─────────────────
# Use "adversarial-review" — a skill name that is stable in this repo.
# The description includes the skill name verbatim.
JSON_MATCH="$(cat <<'EOF'
{
  "tool_name": "Agent",
  "tool_input": {
    "description": "adversarial-review of the current diff",
    "prompt": "Please run a thorough review of the changes."
  }
}
EOF
)"

run_hook "$JSON_MATCH"

if [[ "$HOOK_EXIT" -ne 0 ]]; then
  printf 'FAIL  case-a: hook exited %d (expected 0)\n' "$HOOK_EXIT"
  failures=$((failures + 1))
elif ! printf '%s' "$HOOK_STDERR" | grep -q 'skill-consult:'; then
  printf 'FAIL  case-a: expected a skill-consult nudge on stderr, got none\n'
  printf '      stderr was: %s\n' "$HOOK_STDERR"
  failures=$((failures + 1))
else
  printf 'PASS  case-a: matching description produced nudge, exit 0\n'
  printf '      nudge: %s\n' "$HOOK_STDERR"
fi

# ── Case (b): non-matching description → silence, exit 0 ─────────────────────
JSON_NOMATCH="$(cat <<'EOF'
{
  "tool_name": "Agent",
  "tool_input": {
    "description": "count vowels in a string and return the total",
    "prompt": "Implement a tiny utility that counts vowels."
  }
}
EOF
)"

run_hook "$JSON_NOMATCH"

if [[ "$HOOK_EXIT" -ne 0 ]]; then
  printf 'FAIL  case-b: hook exited %d (expected 0)\n' "$HOOK_EXIT"
  failures=$((failures + 1))
elif [[ -n "$HOOK_STDERR" ]]; then
  printf 'FAIL  case-b: expected silence on stderr, got: %s\n' "$HOOK_STDERR"
  failures=$((failures + 1))
else
  printf 'PASS  case-b: non-matching description produced no nudge, exit 0\n'
fi

# ── Case (c): non-Agent tool → silence, exit 0 ───────────────────────────────
JSON_BASH="$(cat <<'EOF'
{
  "tool_name": "Bash",
  "tool_input": {
    "command": "echo adversarial-review harness-improve"
  }
}
EOF
)"

run_hook "$JSON_BASH"

if [[ "$HOOK_EXIT" -ne 0 ]]; then
  printf 'FAIL  case-c: hook exited %d (expected 0) for non-Agent tool\n' "$HOOK_EXIT"
  failures=$((failures + 1))
elif [[ -n "$HOOK_STDERR" ]]; then
  printf 'FAIL  case-c: non-Agent call produced unexpected stderr: %s\n' "$HOOK_STDERR"
  failures=$((failures + 1))
else
  printf 'PASS  case-c: non-Agent tool produced no output, exit 0\n'
fi

# ── Summary ───────────────────────────────────────────────────────────────────
printf '\n'
if [[ "$failures" -gt 0 ]]; then
  printf 'SELFTEST FAILED: %d case(s) failed\n' "$failures"
  exit 1
else
  printf 'SELFTEST OK: all cases passed\n'
  exit 0
fi
