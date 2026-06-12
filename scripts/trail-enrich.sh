#!/usr/bin/env bash
# PostToolUseFailure hook: appends a !fail event line to the cycle trail.
#
# Event format:
#   !fail::<error-class>::<tool_name>::<input[0:300]>
#
# error-class classification (case-insensitive regex on tool_response):
#   syntax      — "syntax error" or "SyntaxError"
#   test-fail   — "FAILED" or "assert"
#   not-found   — "not found", "No such file", or "command not found"
#   permission  — "Permission denied" or "EACCES"
#   timeout     — "timed out" or "timeout"
#   other       — everything else
#
# Per confirmed empirics (issue #14, 2026-06-11):
#   - PostToolUseFailure fires on failed tool calls (PostToolUse does NOT).
#   - Bash stderr arrives merged into tool_response.stdout (Claude Code 2.1.170,
#     undocumented).  Parse defensively: try .tool_response.stdout first, then
#     .tool_response.error, then .error, then fall back to empty string.
#
# The STATE path reuses cycle-detector.sh's resolution: CLAUDE_PROJECT_DIR or HOME.
# Output: no stdout (PostToolUseFailure stdout goes nowhere; stderr is for debugging
# only and is suppressed here to avoid hook noise).

set -euo pipefail

STATE="${CLAUDE_PROJECT_DIR:-${HOME}}/.claude-cycle-trail"

INPUT="$(cat)"

TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")"
if [[ -z "$TOOL_NAME" ]]; then
  exit 0
fi

TOOL_INPUT_STR="$(printf '%s' "$INPUT" | jq -r '(.tool_input // {} | tostring | .[0:300])' 2>/dev/null || echo "")"

# Extract response text: stdout first (Bash stderr merged there), then .error variants.
RESPONSE_TEXT="$(printf '%s' "$INPUT" | jq -r '
  .tool_response.stdout //
  .tool_response.error //
  .error //
  ""
' 2>/dev/null || echo "")"

# Classify error.
classify_error() {
  local text="$1"
  if printf '%s' "$text" | grep -qiE 'syntax error|SyntaxError'; then
    echo "syntax"
  elif printf '%s' "$text" | grep -qiE 'FAILED|assert'; then
    echo "test-fail"
  elif printf '%s' "$text" | grep -qiE 'not found|No such file|command not found'; then
    echo "not-found"
  elif printf '%s' "$text" | grep -qiE 'Permission denied|EACCES'; then
    echo "permission"
  elif printf '%s' "$text" | grep -qiE 'timed out|timeout'; then
    echo "timeout"
  else
    echo "other"
  fi
}

ERROR_CLASS="$(classify_error "$RESPONSE_TEXT")"

mkdir -p "$(dirname "$STATE")"
printf '!fail::%s::%s::%s\n' "$ERROR_CLASS" "$TOOL_NAME" "$TOOL_INPUT_STR" >> "$STATE"
tail -n 50 "$STATE" > "${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
exit 0
