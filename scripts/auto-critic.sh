#!/usr/bin/env bash
# PreToolUse hook: requires an @critic verdict before any `git push` or `glab mr create`.
# Blocks (exit 2) the mutation and emits an instruction for the lead agent to invoke @critic
# on the full accumulated branch diff / MR draft. The agent re-runs the command after
# creating a single-use marker file (`~/.claude-critic-approved`, TTL 5 minutes) signalling
# that critic returned `approve`. The marker is consumed on use — every subsequent push /
# MR-create needs a fresh critic pass.
#
# Rationale: the @critic sub-agent already exists in this plugin's routing table but is
# invoked only when the lead agent remembers to. The cheapest moments to land neuroslop in
# shared state are the push and the MR-create — commit is local and reversible. Making the
# critic call mandatory at the push boundary means the critic reviews the FULL accumulated
# branch diff once before it lands in shared state, instead of every local commit. Local
# commits stay ungated — the verification gate (verification-gate.sh) still covers them
# with machine checks (shell syntax, Python syntax, JSON validity).
#
# Marker mechanics: single-use, TTL 5 min, consumed on use — every subsequent push /
# MR-create needs a fresh critic pass.
#
# Bypass for small fixups: `touch ~/.claude-critic-approved && <command>`. Use intentionally,
# the risk is on the developer.

set -euo pipefail

INPUT="$(cat)"

TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")"
[[ "$TOOL_NAME" == "Bash" ]] || exit 0

COMMAND="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")"
[[ -n "$COMMAND" ]] || exit 0

matches=0
if printf '%s' "$COMMAND" | grep -qE '(^|[[:space:];&|(])git[[:space:]]+push([[:space:]]|$)'; then
  matches=1
fi
if printf '%s' "$COMMAND" | grep -qE '(^|[[:space:];&|(])glab[[:space:]]+mr[[:space:]]+create([[:space:]]|$)'; then
  matches=1
fi
[[ "$matches" -eq 1 ]] || exit 0

MARKER="${HOME}/.claude-critic-approved"
if [[ -f "$MARKER" ]]; then
  NOW=$(date +%s)
  MTIME=$(stat -c %Y "$MARKER" 2>/dev/null || stat -f %m "$MARKER" 2>/dev/null || echo "$NOW")
  AGE=$(( NOW - MTIME ))
  rm -f "$MARKER"
  if [[ "$AGE" -le 300 ]]; then
    exit 0
  fi
  # Stale marker treated as missing; fall through to block.
fi

cat >&2 <<'EOF'
auto-critic: a mandatory critic check is required before this mutation.

1. Invoke the critic sub-agent with:
   - for `git push` — the full branch diff (`git diff @{upstream}...HEAD`, or `git diff origin/<default-branch>...HEAD` when the branch has no upstream yet) plus the branch name and intended PR/MR summary;
   - for `glab mr create` — the MR title, description, and a diff summary.
   Include an `<inherited-invariants>` block (use `scripts/role-invariants.sh critic`) in the prompt.
   If the `critic` subagent_type from this plugin (`neuro-matrix:critic`) is not registered
   in the current environment, fall back to `general-purpose` with the body of `agents/critic.md`
   as the system-prompt template. The role contract is stable; the binding is not.

2. If critic returns `approve`:
       touch ~/.claude-critic-approved
       <re-run the original command>

3. If critic returns `fix-required` — address the flagged items first, then loop again from step 1.

Intentional bypass (small fixup, risk accepted): `touch ~/.claude-critic-approved && <command>`.
EOF
exit 2
