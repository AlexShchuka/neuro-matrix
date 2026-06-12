#!/usr/bin/env bash
# PreToolUse hook: enforces "halt on no-progress" — blocks (exit 2) when the same
# (tool_name, tool_input) signature has been used in the last 2 PreToolUse calls,
# i.e., the agent is about to attempt the same action for a third time in a row.
#
# Rationale: per the plugin protocol, two consecutive actions without progress should
# stop and ask. The third attempt is exactly the moment to interrupt.

set -euo pipefail

STATE="${CLAUDE_PROJECT_DIR:-${HOME}}/.claude-cycle-trail"

INPUT="$(cat)"

# Build a signature: tool_name + first 300 chars of stringified tool_input.
# Falls back to empty string if jq is missing or the input is malformed; in that
# case the hook silently passes (we never block on parser failure).
SIG="$(printf '%s' "$INPUT" | jq -r '"\(.tool_name // "")::\(.tool_input // {} | tostring | .[0:300])"' 2>/dev/null || echo "")"

if [[ -z "$SIG" ]]; then
  exit 0
fi

# Detect revert/reset/checkout -- commands and append a trail event before the
# normal signature line.  Matching is intentionally loose (any word-boundary
# appearance of the command patterns in a Bash tool call).
REVERT_INPUT=""
if [[ "$SIG" == Bash::* ]]; then
  RAW_INPUT="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || true)"
  if printf '%s' "$RAW_INPUT" | grep -qE '(^|[[:space:]])git[[:space:]]+(revert|reset[[:space:]]+--hard|checkout[[:space:]]+\-\-)'; then
    REVERT_INPUT="$(printf '%s' "$RAW_INPUT" | head -c 300)"
  fi
fi

if [[ -f "$STATE" ]]; then
  # Ignore event lines (start with '!') when checking for repeated signatures.
  COUNT="$(grep -v '^!' "$STATE" | tail -n 2 | grep -Fxc -- "$SIG" || true)"
  if [[ "${COUNT:-0}" -ge 2 ]]; then
    echo "halt-on-no-progress: same tool+input attempted 3 times in a row. Stop, reassess, and ask the user before retrying." >&2
    exit 2
  fi
fi

mkdir -p "$(dirname "$STATE")"
if [[ -n "$REVERT_INPUT" ]]; then
  printf '!revert::%s\n' "$REVERT_INPUT" >> "$STATE"
fi
echo "$SIG" >> "$STATE"
tail -n 50 "$STATE" > "${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
exit 0
