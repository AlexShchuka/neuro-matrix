#!/usr/bin/env bash
# PreToolUse hook: requires a DUAL CO-SIGN before any `git push` or `glab mr create`.
# Blocks (exit 2) the mutation until BOTH co-sign markers are present and fresh, then
# consumes them (single-use). This replaces the former sha-verdict scheme — there is no
# longer any sha256 of the diff, and no git-diff hashing at all. Removing the hash compare
# kills the rtk-wraps-git-diff mismatch pain: the gate no longer depends on the exact bytes
# of `git diff` (which rtk and other wrappers can perturb), only on two co-sign markers.
#
# Co-sign model (C2): the push unlocks IFF BOTH co-signers have signed:
#   ~/.claude-cosign-owner   containing the line:  cosign: owner
#   ~/.claude-cosign-claude  containing the line:  cosign: claude
# Each marker is fresh (TTL 300 s) and single-use (consumed with `rm -f` on check). The two
# co-signers are the owner and Claude — the same pair that co-reviews the storozh flags. The
# push is the moment they both put their name on what lands in shared state.
#
# Marker contract (one required line each):
#   ~/.claude-cosign-owner   →  cosign: owner
#   ~/.claude-cosign-claude  →  cosign: claude
# Any missing marker, stale marker (age > 300 s), empty marker, or wrong/absent cosign line
# → block (exit 2). Both markers are consumed on every check (pass or block), so each retry
# requires BOTH co-signers to sign again — there is no partial-credit and no single-use bypass.
#
# Trust-model limitation: the hook cannot technically verify WHO wrote each marker — it only
# verifies the file exists, is fresh, and carries the right cosign line. The owner marker is
# meant to be written by the human owner; writing ~/.claude-cosign-owner from inside the agent
# is a protocol violation (the gate is a friction point and an audit trail, not a cryptographic
# proof). The same trust model that governed the former human-token gate applies here.
#
# Protocol-path rule (STRICT, no degradation): for protocol-artifact paths
# (invariants*, agents/, hooks/, skills/, eval/, references/protocol/, scripts/, CLAUDE.md —
# see protocol_path_matches()) BOTH markers are required by exactly the same rule — there is
# NO bypass and NO degraded single-marker path. Because both markers are always required for
# every push, a protocol-path push is held to the identical bar as any other push; the
# protocol-path detection is retained as an audit signal in the block message, not as a second,
# weaker gate. Fail-closed on any missing marker, for protocol and non-protocol paths alike.
#
# Rationale: the cheapest moment to land neuroslop in shared state is the push / MR-create —
# commit is local and reversible. Requiring two independent co-signs (owner AND Claude) at the
# push boundary means neither co-signer alone can land shared state, and the storozh advisory
# flags (skills/storozh) are co-reviewed by exactly this pair before they sign. Local commits
# stay ungated — the verification gate (verification-gate.sh) still covers them with machine
# checks (shell syntax, Python syntax, JSON validity).
#
# Marker mechanics: single-use, TTL 300 s, consumed on check — every subsequent push /
# MR-create needs a fresh pair of co-sign markers.

set -euo pipefail

# Source protocol-path helper (defines protocol_path_matches()).
# Path is resolved relative to this script's own location so it works
# regardless of CWD or how ${CLAUDE_PLUGIN_ROOT} is set at hook runtime.
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=protocol-paths.sh
. "${_SCRIPT_DIR}/protocol-paths.sh"

INPUT="$(cat)"

TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")"
[[ "$TOOL_NAME" == "Bash" ]] || exit 0

COMMAND="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")"
[[ -n "$COMMAND" ]] || exit 0

# Push detector. `git` may carry intervening GLOBAL options before the `push` subcommand
# (e.g. `git -C <path> push`, `git --git-dir=... push`, `git -c k=v push`). The former
# matcher required `git` immediately followed by `push`, so any global option slipped the
# gate entirely (ungated push) — exactly what this gate exists to stop. The group below
# tolerates zero or more global-option tokens between `git` and `push`: each is a dash
# option (`-x` / `--x[=v]`), optionally followed by ONE non-dash argument token (`-C` takes
# a path, `--git-dir` may take a separate value). It deliberately does NOT swallow `push`
# itself (a non-dash token is only consumed right after a dash option), so `git push` and
# `git -C /tmp/x push` both match while bare subcommands like `git status` do not.
matches=0
if printf '%s' "$COMMAND" | grep -qE '(^|[[:space:];&|(])git[[:space:]]+(-[^[:space:]]+([[:space:]]+[^-][^[:space:]]*)?[[:space:]]+)*push([[:space:]]|$)'; then
  matches=1
fi
if printf '%s' "$COMMAND" | grep -qE '(^|[[:space:];&|(])glab[[:space:]]+mr[[:space:]]+create([[:space:]]|$)'; then
  matches=1
fi
[[ "$matches" -eq 1 ]] || exit 0

COSIGN_OWNER="${HOME}/.claude-cosign-owner"
COSIGN_CLAUDE="${HOME}/.claude-cosign-claude"
COSIGN_TTL=300

# check_cosign <marker-path> <expected-role>
#   Validates one co-sign marker. ALWAYS consumes the marker if it exists (single-use),
#   whether it passes or fails. Echoes a one-line reason to stdout on failure (caller routes
#   it to the block message); returns 0 on a valid, fresh, correctly-signed marker, else 1.
check_cosign() {
  local marker="$1" role="$2"
  local now mtime age content line

  if [[ ! -f "$marker" ]]; then
    echo "missing marker ${marker} (cosign: ${role})"
    return 1
  fi

  now=$(date +%s)
  mtime=$(stat -c %Y "$marker" 2>/dev/null || stat -f %m "$marker" 2>/dev/null || echo "$now")
  age=$(( now - mtime ))

  # Always consume (single-use), whether we pass or block.
  content="$(cat "$marker")"
  rm -f "$marker"

  if [[ "$age" -gt "$COSIGN_TTL" ]]; then
    echo "stale marker ${marker} (age ${age}s > ${COSIGN_TTL}s TTL) — cosign: ${role} must be re-signed"
    return 1
  fi

  # Empty / bare touch → reject.
  if [[ -z "$content" ]] || ! printf '%s' "$content" | grep -q '.'; then
    echo "empty marker ${marker} — a bare touch does not satisfy the gate; write the line 'cosign: ${role}'"
    return 1
  fi

  # Require the exact cosign line for this role.
  line="$(printf '%s' "$content" | grep "^cosign: ${role}$" | head -1 || true)"
  if [[ -z "$line" ]]; then
    echo "marker ${marker} is missing the required line 'cosign: ${role}'"
    return 1
  fi

  return 0
}

# Detect whether any changed path is a protocol artifact (audit signal only — the rule below
# is identical for protocol and non-protocol paths: BOTH markers required, strictly).
# Resolve default branch dynamically; fall back to origin/main. The diff is used ONLY to list
# changed names for the audit signal — there is NO hashing of its contents anywhere.
DEFAULT_REF="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/||' || echo "origin/main")"
PROTOCOL_CHANGED=0
MATCHED_PATHS=""
while IFS= read -r changed_path; do
  [[ -n "$changed_path" ]] || continue
  if protocol_path_matches "$changed_path"; then
    PROTOCOL_CHANGED=1
    MATCHED_PATHS="${MATCHED_PATHS}  ${changed_path}"$'\n'
  fi
done < <(git diff --name-only "${DEFAULT_REF}...HEAD" 2>/dev/null || true)

# Evaluate BOTH co-sign markers. check_cosign always consumes, so both are read (and removed)
# on every invocation — no partial-credit, no single-marker degraded path.
# Declare-then-assign with `|| OK=$?` so a non-zero check_cosign (the common missing-marker
# path) does not trip `set -e` before the rc is captured — the guard keeps each statement's
# own status zero, mirroring the DIFF_RC pattern the former hash-gate used.
OWNER_OK=0
OWNER_REASON="$(check_cosign "$COSIGN_OWNER" owner)" || OWNER_OK=$?
CLAUDE_OK=0
CLAUDE_REASON="$(check_cosign "$COSIGN_CLAUDE" claude)" || CLAUDE_OK=$?

if [[ "$OWNER_OK" -eq 0 && "$CLAUDE_OK" -eq 0 ]]; then
  # Both co-signers present, fresh, valid — and now consumed. Push unlocks.
  exit 0
fi

# Fail CLOSED: at least one marker is missing / stale / invalid. Emit the block message and
# exit 2 (PreToolUse blocks only on exit 2).
{
  echo "auto-critic: push BLOCKED — a DUAL CO-SIGN is required before this mutation (fail-closed)."
  echo
  echo "Both co-sign markers must be present, fresh (TTL ${COSIGN_TTL}s), and single-use:"
  echo "  ~/.claude-cosign-owner   containing:  cosign: owner"
  echo "  ~/.claude-cosign-claude  containing:  cosign: claude"
  echo
  echo "Status this attempt (both markers are consumed on every check — re-sign both to retry):"
  if [[ "$OWNER_OK" -eq 0 ]]; then
    echo "  owner  : OK (consumed)"
  else
    echo "  owner  : MISSING/INVALID — ${OWNER_REASON}"
  fi
  if [[ "$CLAUDE_OK" -eq 0 ]]; then
    echo "  claude : OK (consumed)"
  else
    echo "  claude : MISSING/INVALID — ${CLAUDE_REASON}"
  fi
  echo
  if [[ "$PROTOCOL_CHANGED" -eq 1 ]]; then
    echo "Protocol-artifact paths are in this diff (audit signal):"
    printf '%s' "$MATCHED_PATHS"
    echo "The rule is the SAME as any other push — BOTH markers, strictly, no bypass and no"
    echo "single-marker degradation. Protocol paths get no weaker and no stronger gate here."
    echo
  fi
  echo "To unlock the push, BOTH co-signers sign (each as a SEPARATE command), then re-run the"
  echo "original command. The owner marker MUST be written by the human owner — writing"
  echo "~/.claude-cosign-owner from inside the agent is a protocol violation (friction point and"
  echo "audit trail, not cryptographic proof)."
  echo
  echo "  # owner co-sign (run by the human owner in the Claude Code prompt):"
  echo "  ! printf 'cosign: owner\\n' > ~/.claude-cosign-owner"
  echo
  echo "  # claude co-sign (after the co-review of the storozh flags / branch diff):"
  echo "  printf 'cosign: claude\\n' > ~/.claude-cosign-claude"
  echo
  echo "Both markers expire after ${COSIGN_TTL}s and are consumed on use — sign both within the"
  echo "window, then push."
} >&2
exit 2
