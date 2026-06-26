#!/usr/bin/env bash
# selftest_auto-critic.sh — regression probe for scripts/auto-critic.sh (dual co-sign gate).
#
# Exercises the C2 co-sign scheme that REPLACED the former sha-verdict logic:
#   push unlocks IFF BOTH ~/.claude-cosign-owner (cosign: owner) AND
#   ~/.claude-cosign-claude (cosign: claude) are present, fresh (TTL 300s), then consumed.
# There is no sha256 / git-diff hashing anywhere; the protocol-path rule is STRICT (both
# markers, no bypass, no single-marker degradation) and fail-closed on any missing marker.
#
# Each case runs the hook with a fresh fake $HOME (so markers do not leak between cases) and
# a throwaway git repo with origin/main set (so the protocol-path audit signal can diff).
# Asserts on the exit code (0 = unlock, 2 = block) and on marker consumption (single-use).
#
# Usage: bash scripts/selftest_auto-critic.sh
# Run from anywhere; paths resolve relative to this script's own location.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$HERE/auto-critic.sh"

if [[ ! -f "$HOOK" ]]; then
  printf 'selftest: ERROR: hook not found: %s\n' "$HOOK" >&2
  exit 1
fi

failures=0
pass=0

# fail <case> <msg>
fail() { printf 'FAIL  %s: %s\n' "$1" "$2"; failures=$((failures + 1)); }
ok()   { pass=$((pass + 1)); }

# Build a throwaway git repo with an origin/main base ref and a protocol-path change on HEAD,
# so `git diff --name-only origin/main...HEAD` lists a protocol artifact (scripts/x.sh).
make_repo() {
  local repo="$1"
  git init -q "$repo"
  (
    cd "$repo"
    git config user.email t@t; git config user.name t
    git symbolic-ref HEAD refs/heads/main
    mkdir -p scripts
    echo base > scripts/x.sh
    git add -A; git commit -q -m base
    # Simulate a remote default branch pointing at the base commit.
    git update-ref refs/remotes/origin/main HEAD
    git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
    # Advance HEAD with a protocol-path change so the diff is non-empty.
    echo changed > scripts/x.sh
    git add -A; git commit -q -m change
  )
}

# Build a throwaway repo whose HEAD change touches ONLY a non-protocol path (a docs file),
# so `protocol_path_matches` never fires and the hook runs its PROTOCOL_CHANGED=0 branch.
# README.md is not in protocol_path_matches()'s set, so the protocol-path audit block is
# absent from the block message for this fixture.
make_repo_nonproto() {
  local repo="$1"
  git init -q "$repo"
  (
    cd "$repo"
    git config user.email t@t; git config user.name t
    git symbolic-ref HEAD refs/heads/main
    echo base > README.md
    git add -A; git commit -q -m base
    git update-ref refs/remotes/origin/main HEAD
    git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
    # Advance HEAD with a NON-protocol (docs) change so the diff is non-empty but not a
    # protocol artifact.
    echo changed > README.md
    git add -A; git commit -q -m change
  )
}

# run_case <home-dir> <repo-dir> -> sets RC to the hook exit code.
# Feeds a `git push` Bash tool_use event on stdin, with HOME and CWD pointed at the fixtures.
run_case() {
  run_case_cmd "$1" "$2" "git push origin HEAD"
}

# run_case_cmd <home-dir> <repo-dir> <command> -> sets RC to the hook exit code and MSG to
# the captured block message (stderr). Lets a case assert on the block-message CONTENT (e.g.
# the protocol-path audit line) as well as the exit code, and lets a case feed an arbitrary
# git invocation (e.g. `git -C <path> push ...`) to prove the broadened matcher intercepts it.
run_case_cmd() {
  local home="$1" repo="$2" cmd="$3"
  local input
  input="$(jq -nc --arg c "$cmd" '{tool_name:"Bash",tool_input:{command:$c}}')"
  RC=0
  MSG="$( ( cd "$repo" && printf '%s' "$input" | HOME="$home" bash "$HOOK" ) 2>&1 1>/dev/null )" || RC=$?
}

sign() { printf 'cosign: %s\n' "$2" > "$1"; }

# ── Case 1: both markers present & fresh → unlock (exit 0), both consumed ───────
H="$(mktemp -d)"; R="$(mktemp -d)/repo"; make_repo "$R"
sign "$H/.claude-cosign-owner" owner
sign "$H/.claude-cosign-claude" claude
run_case "$H" "$R"
if [[ "$RC" -eq 0 ]]; then ok; else fail "both-present" "expected exit 0 (unlock), got $RC"; fi
if [[ ! -f "$H/.claude-cosign-owner" && ! -f "$H/.claude-cosign-claude" ]]; then ok
else fail "both-present-consume" "markers not consumed (single-use violated)"; fi
rm -rf "$H" "$R"

# ── Case 2: only owner present → block (exit 2), owner consumed ─────────────────
H="$(mktemp -d)"; R="$(mktemp -d)/repo"; make_repo "$R"
sign "$H/.claude-cosign-owner" owner
run_case "$H" "$R"
if [[ "$RC" -eq 2 ]]; then ok; else fail "owner-only" "expected exit 2 (block), got $RC"; fi
if [[ ! -f "$H/.claude-cosign-owner" ]]; then ok
else fail "owner-only-consume" "owner marker not consumed on block"; fi
rm -rf "$H" "$R"

# ── Case 3: only claude present → block (exit 2) ───────────────────────────────
H="$(mktemp -d)"; R="$(mktemp -d)/repo"; make_repo "$R"
sign "$H/.claude-cosign-claude" claude
run_case "$H" "$R"
if [[ "$RC" -eq 2 ]]; then ok; else fail "claude-only" "expected exit 2 (block), got $RC"; fi
rm -rf "$H" "$R"

# ── Case 4: no markers → block (exit 2), fail-closed ───────────────────────────
H="$(mktemp -d)"; R="$(mktemp -d)/repo"; make_repo "$R"
run_case "$H" "$R"
if [[ "$RC" -eq 2 ]]; then ok; else fail "none" "expected exit 2 (fail-closed block), got $RC"; fi
rm -rf "$H" "$R"

# ── Case 5: both present but wrong cosign line in owner → block (exit 2) ────────
H="$(mktemp -d)"; R="$(mktemp -d)/repo"; make_repo "$R"
printf 'cosign: claude\n' > "$H/.claude-cosign-owner"   # wrong role in owner file
sign "$H/.claude-cosign-claude" claude
run_case "$H" "$R"
if [[ "$RC" -eq 2 ]]; then ok; else fail "wrong-role" "expected exit 2 (block), got $RC"; fi
rm -rf "$H" "$R"

# ── Case 6: stale owner marker (mtime > 300s ago) → block (exit 2) ─────────────
H="$(mktemp -d)"; R="$(mktemp -d)/repo"; make_repo "$R"
sign "$H/.claude-cosign-owner" owner
sign "$H/.claude-cosign-claude" claude
touch -d '@'"$(( $(date +%s) - 600 ))" "$H/.claude-cosign-owner" 2>/dev/null \
  || touch -t "$(date -v-600S +%Y%m%d%H%M.%S 2>/dev/null || echo 197001010000)" "$H/.claude-cosign-owner"
run_case "$H" "$R"
if [[ "$RC" -eq 2 ]]; then ok; else fail "stale-owner" "expected exit 2 (stale block), got $RC"; fi
rm -rf "$H" "$R"

# ── Case 7: empty (bare touch) owner marker → block (exit 2) ───────────────────
H="$(mktemp -d)"; R="$(mktemp -d)/repo"; make_repo "$R"
: > "$H/.claude-cosign-owner"   # bare touch, empty
sign "$H/.claude-cosign-claude" claude
run_case "$H" "$R"
if [[ "$RC" -eq 2 ]]; then ok; else fail "empty-owner" "expected exit 2 (block), got $RC"; fi
rm -rf "$H" "$R"

# ── Case 8: non-push command is ignored (exit 0, no gate) ──────────────────────
H="$(mktemp -d)"; R="$(mktemp -d)/repo"; make_repo "$R"
RC=0
( cd "$R" && printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git status"}}' \
  | HOME="$H" bash "$HOOK" ) >/dev/null 2>&1 || RC=$?
if [[ "$RC" -eq 0 ]]; then ok; else fail "non-push" "expected exit 0 (ignored), got $RC"; fi
rm -rf "$H" "$R"

# ── Case 9: `git -C <path> push` is now intercepted (N-min1 regression) ────────
# The former matcher required `git` immediately followed by `push`, so a global option such
# as `-C <path>` slipped the gate entirely (ungated push). With no markers present the
# broadened matcher must catch it and fail closed (exit 2). If the regex were still narrow
# the hook would `exit 0` here (RC=0) and this assertion would fail.
H="$(mktemp -d)"; R="$(mktemp -d)/repo"; make_repo "$R"
run_case_cmd "$H" "$R" "git -C /tmp/x push origin main"
if [[ "$RC" -eq 2 ]]; then ok; else fail "git-C-push-intercept" "expected exit 2 (intercepted+blocked), got $RC"; fi
rm -rf "$H" "$R"

# ── Case 10: protocol-path push emits the protocol-path audit line in the block ─
# A protocol artifact (scripts/x.sh, via make_repo) is in the diff, so the block message
# must carry the protocol-path audit section. Assert on message CONTENT, not just exit code.
H="$(mktemp -d)"; R="$(mktemp -d)/repo"; make_repo "$R"
run_case_cmd "$H" "$R" "git push origin HEAD"
if [[ "$RC" -eq 2 ]]; then ok; else fail "proto-audit-rc" "expected exit 2 (block), got $RC"; fi
if printf '%s' "$MSG" | grep -q 'Protocol-artifact paths are in this diff'; then ok
else fail "proto-audit-line" "block message missing protocol-path audit line for a protocol-path push"; fi
if printf '%s' "$MSG" | grep -q 'scripts/x.sh'; then ok
else fail "proto-audit-path" "block message did not list the changed protocol path scripts/x.sh"; fi
rm -rf "$H" "$R"

# ── Case 11: NON-protocol-path push (PROTOCOL_CHANGED=0) → block, NO audit line ─
# README.md change only → protocol_path_matches never fires, exercising the hook's
# PROTOCOL_CHANGED=0 branch (previously untested — make_repo always staged a protocol path).
# Still fail-closed (exit 2, no markers), but the protocol-path audit section is ABSENT.
H="$(mktemp -d)"; R="$(mktemp -d)/repo"; make_repo_nonproto "$R"
run_case_cmd "$H" "$R" "git push origin HEAD"
if [[ "$RC" -eq 2 ]]; then ok; else fail "nonproto-rc" "expected exit 2 (fail-closed block), got $RC"; fi
if printf '%s' "$MSG" | grep -q 'Protocol-artifact paths are in this diff'; then
  fail "nonproto-no-audit" "block message wrongly carried the protocol-path audit line for a non-protocol push"
else ok; fi
rm -rf "$H" "$R"

printf '\n'
if [[ "$failures" -gt 0 ]]; then
  printf 'SELFTEST FAILED: %d assertion(s) failed (dual co-sign gate)\n' "$failures"
  exit 1
else
  printf 'SELFTEST OK: %d assertions passed (dual co-sign gate)\n' "$pass"
  exit 0
fi
