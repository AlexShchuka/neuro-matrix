#!/usr/bin/env bash
# selftest_trail.sh — regression probe for trail-enrichment scripts and the
# cycle-detector counting fix.
#
# Tests:
#   T1 — cycle-detector blocks the literal 3rd identical attempt when event
#        lines are interleaved between signature lines.
#   T2 — cycle-detector does NOT false-block when signatures differ.
#   T3 — trail-enrich.sh classifies one sample payload per error-class correctly.
#   T4 — trail-interrupt.sh emits !interrupt on a marker prompt and is silent
#        (exit 0, no output) otherwise.
#   T5 — auto-critic.sh: bash -n syntax check.
#   T6 — auto-critic.sh: path-matching logic unit test (simulated changed-path
#        matching the protocol-path set).
#
# Usage: bash scripts/selftest_trail.sh
# Run from the repository root or any directory; paths are resolved relative to
# this script's own location.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DETECTOR="$HERE/cycle-detector.sh"
ENRICH="$HERE/trail-enrich.sh"
INTERRUPT="$HERE/trail-interrupt.sh"
CRITIC="$HERE/auto-critic.sh"
PROTO_HELPER="$HERE/protocol-paths.sh"

# Source the canonical protocol-path helper so T6 tests the real function,
# not a hand-copied duplicate that can silently diverge.
# shellcheck source=protocol-paths.sh
. "$PROTO_HELPER"

failures=0
pass=0

fail() {
  printf 'FAIL  %s\n' "$1"
  failures=$((failures + 1))
}

ok() {
  printf 'ok    %s\n' "$1"
  pass=$((pass + 1))
}

# ── T1: cycle-detector blocks 3rd identical attempt with interleaved events ──
T1_DIR="$(mktemp -d)"
T1_STATE="$T1_DIR/.claude-cycle-trail"
SIG='Bash::{"command":"ls"}'

# Simulate: sig, !fail event, sig, !fail event — so trail has 2 sigs but 4 lines total.
printf '%s\n!fail::other::Bash::{"command":"ls"}\n%s\n!fail::other::Bash::{"command":"ls"}\n' \
  "$SIG" "$SIG" > "$T1_STATE"

T1_INPUT='{"tool_name":"Bash","tool_input":{"command":"ls"}}'
T1_OUT="$(CLAUDE_PROJECT_DIR="$T1_DIR" bash "$DETECTOR" <<< "$T1_INPUT" 2>&1; true)"
T1_RC=0
CLAUDE_PROJECT_DIR="$T1_DIR" bash "$DETECTOR" <<< "$T1_INPUT" >/dev/null 2>&1 || T1_RC=$?

if [[ "$T1_RC" -eq 2 ]]; then
  ok "T1: cycle-detector blocks 3rd identical sig with interleaved event lines"
else
  fail "T1: cycle-detector did not block (exit rc=$T1_RC); expected exit 2"
fi
rm -rf "$T1_DIR"

# ── T2: cycle-detector does NOT false-block when signatures differ ────────────
T2_DIR="$(mktemp -d)"
T2_STATE="$T2_DIR/.claude-cycle-trail"
SIG_A='Bash::{"command":"ls -la"}'
SIG_B='Bash::{"command":"pwd"}'

printf '%s\n%s\n' "$SIG_A" "$SIG_B" > "$T2_STATE"

T2_INPUT='{"tool_name":"Bash","tool_input":{"command":"ls -la"}}'
T2_RC=0
CLAUDE_PROJECT_DIR="$T2_DIR" bash "$DETECTOR" <<< "$T2_INPUT" >/dev/null 2>&1 || T2_RC=$?

if [[ "$T2_RC" -eq 0 ]]; then
  ok "T2: cycle-detector does not false-block on differing signatures"
else
  fail "T2: cycle-detector false-blocked (exit rc=$T2_RC); expected exit 0"
fi
rm -rf "$T2_DIR"

# ── T3: trail-enrich classifies error-classes correctly ──────────────────────
enrich_classify() {
  local label="$1"
  local response_text="$2"
  local expected_class="$3"

  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local tmp_state="$tmp_dir/.claude-cycle-trail"

  local input
  input="$(printf '{"tool_name":"Bash","tool_input":{"command":"test"},"tool_response":{"stdout":"%s"}}' \
    "$(printf '%s' "$response_text" | sed 's/"/\\"/g')")"

  CLAUDE_PROJECT_DIR="$tmp_dir" bash "$ENRICH" <<< "$input" >/dev/null 2>&1

  if [[ -f "$tmp_state" ]]; then
    local line
    line="$(cat "$tmp_state")"
    local got_class
    got_class="$(printf '%s' "$line" | sed 's/^!fail::\([^:]*\)::.*/\1/')"
    if [[ "$got_class" == "$expected_class" ]]; then
      ok "T3[$label]: enrich classifies '$expected_class' correctly"
    else
      fail "T3[$label]: expected class '$expected_class', got '$got_class' (line: $line)"
    fi
  else
    fail "T3[$label]: no trail file written by trail-enrich.sh"
  fi
  rm -rf "$tmp_dir"
}

enrich_classify "syntax"     "SyntaxError: unexpected token"         "syntax"
enrich_classify "test-fail"  "3 tests FAILED in suite"               "test-fail"
enrich_classify "not-found"  "bash: foo: command not found"          "not-found"
enrich_classify "permission" "Permission denied: /etc/shadow"        "permission"
enrich_classify "timeout"    "process timed out after 30s"           "timeout"
enrich_classify "other"      "some unrecognised error message here"  "other"

# ── T4: trail-interrupt.sh ────────────────────────────────────────────────────
# T4a: emits !interrupt on marker prompt.
T4A_DIR="$(mktemp -d)"
T4A_STATE="$T4A_DIR/.claude-cycle-trail"
T4A_INPUT='{"prompt":"Hello [Request interrupted by user] continuing..."}'
T4A_STDOUT="$(CLAUDE_PROJECT_DIR="$T4A_DIR" bash "$INTERRUPT" <<< "$T4A_INPUT")"

if [[ -f "$T4A_STATE" ]] && grep -qxF '!interrupt' "$T4A_STATE"; then
  if [[ -z "$T4A_STDOUT" ]]; then
    ok "T4a: trail-interrupt writes !interrupt and produces no stdout"
  else
    fail "T4a: trail-interrupt wrote !interrupt but produced stdout: '$T4A_STDOUT'"
  fi
else
  fail "T4a: trail-interrupt did not write !interrupt line to trail"
fi
rm -rf "$T4A_DIR"

# T4b: silent + exit 0 on normal prompt.
T4B_DIR="$(mktemp -d)"
T4B_STATE="$T4B_DIR/.claude-cycle-trail"
T4B_INPUT='{"prompt":"What is the capital of France?"}'
T4B_STDOUT="$(CLAUDE_PROJECT_DIR="$T4B_DIR" bash "$INTERRUPT" <<< "$T4B_INPUT")"
T4B_RC=0
CLAUDE_PROJECT_DIR="$T4B_DIR" bash "$INTERRUPT" <<< "$T4B_INPUT" >/dev/null 2>&1 || T4B_RC=$?

if [[ "$T4B_RC" -eq 0 ]] && [[ -z "$T4B_STDOUT" ]] && [[ ! -f "$T4B_STATE" || ! -s "$T4B_STATE" ]]; then
  ok "T4b: trail-interrupt is silent and exits 0 on normal prompt"
else
  fail "T4b: trail-interrupt had unexpected output or state write (rc=$T4B_RC stdout='$T4B_STDOUT')"
fi
rm -rf "$T4B_DIR"

# ── T5: bash -n syntax check on all touched scripts ──────────────────────────
for script in "$DETECTOR" "$ENRICH" "$INTERRUPT" "$CRITIC" "$PROTO_HELPER"; do
  if bash -n "$script" 2>/dev/null; then
    ok "T5[bash -n]: $script"
  else
    fail "T5[bash -n]: $script failed syntax check"
  fi
done

# ── T6: auto-critic protocol-path matching unit test ─────────────────────────
# protocol_path_matches() is sourced from protocol-paths.sh above — any drift
# in auto-critic.sh's case block will be caught here automatically.

assert_protocol() {
  local path="$1"
  local expect_match="$2"  # "yes" or "no"
  if protocol_path_matches "$path"; then
    actual="yes"
  else
    actual="no"
  fi
  if [[ "$actual" == "$expect_match" ]]; then
    ok "T6[path-match $expect_match]: '$path'"
  else
    fail "T6[path-match]: '$path' expected=$expect_match got=$actual"
  fi
}

assert_protocol "invariants.txt"               "yes"
assert_protocol "CLAUDE.md"                    "yes"
assert_protocol "agents/critic.md"             "yes"
assert_protocol "hooks/hooks.json"             "yes"
assert_protocol "eval/probes.py"               "yes"
assert_protocol "references/protocol/co-system.md" "yes"
assert_protocol "scripts/auto-critic.sh"       "yes"
assert_protocol "scripts/cycle-detector.sh"   "yes"
assert_protocol "README.md"                    "no"
assert_protocol "ROADMAP.md"                   "no"
assert_protocol "docs/design.md"               "no"
assert_protocol "references/per-stack/bash.md" "no"
assert_protocol "common-code.sample.jsonl"     "no"

# ── Summary ───────────────────────────────────────────────────────────────────
printf '\n'
if [[ "$failures" -gt 0 ]]; then
  printf 'SELFTEST FAILED: %d tests failed, %d passed\n' "$failures" "$pass"
  exit 1
else
  printf 'SELFTEST OK: %d tests passed\n' "$pass"
  exit 0
fi
