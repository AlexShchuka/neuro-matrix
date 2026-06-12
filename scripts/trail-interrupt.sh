#!/usr/bin/env bash
# UserPromptSubmit hook: appends a !interrupt event line to the cycle trail
# when the user prompt contains "[Request interrupted by user]".
#
# Event format:
#   !interrupt
#
# IMPORTANT — stdout discipline: UserPromptSubmit stdout is injected verbatim
# into the prompt context.  This script MUST produce NO stdout unless it is
# emitting intentional prompt injection.  The !interrupt line is written to the
# STATE file only; stdout is strictly suppressed.  Use stderr for debug output
# only (and only when debugging — keep silent in production).
#
# The STATE path reuses cycle-detector.sh's resolution: CLAUDE_PROJECT_DIR or HOME.

set -euo pipefail

STATE="${CLAUDE_PROJECT_DIR:-${HOME}}/.claude-cycle-trail"

INPUT="$(cat)"

PROMPT_TEXT="$(printf '%s' "$INPUT" | jq -r '.prompt // ""' 2>/dev/null || echo "")"

if printf '%s' "$PROMPT_TEXT" | grep -qF '[Request interrupted by user]'; then
  mkdir -p "$(dirname "$STATE")"
  printf '!interrupt\n' >> "$STATE"
  tail -n 50 "$STATE" > "${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
fi

# Always exit 0 silently — no stdout under any branch.
exit 0
