#!/usr/bin/env bash
# PreToolUse hook: requires an @critic verdict before any `git push` or `glab mr create`.
# Blocks (exit 2) the mutation and emits an instruction for the lead agent to invoke @critic
# on the full accumulated branch diff / MR draft. The agent re-runs the command after
# writing a verdict file (`~/.claude-critic-approved`, TTL 5 minutes, single-use) that
# records the critic's decision and a SHA-256 of the exact diff that was reviewed.
# The marker is consumed on use — every subsequent push / MR-create needs a fresh critic pass.
#
# Rationale: the @critic sub-agent already exists in this plugin's routing table but is
# invoked only when the lead agent remembers to. The cheapest moments to land neuroslop in
# shared state are the push and the MR-create — commit is local and reversible. Making the
# critic call mandatory at the push boundary means the critic reviews the FULL accumulated
# branch diff once before it lands in shared state, instead of every local commit. Local
# commits stay ungated — the verification gate (verification-gate.sh) still covers them
# with machine checks (shell syntax, Python syntax, JSON validity).
#
# Verdict file contract (both lines required, order-insensitive):
#   verdict: approve
#   diff-sha256: <sha256 of the exact bytes of git diff origin/<default-branch>...HEAD>
#
# The hook recomputes the sha256 at push time and compares; any mismatch, missing field,
# missing file, or expired TTL → block (exit 2).
#
# Owner escape hatch: a verdict file containing the line `bypass: owner-accepted-risk`
# skips the hash check entirely, but the hook prints a prominent stderr warning and still
# consumes the marker. An empty / bare `touch` file is rejected outright — it no longer
# satisfies the gate.
#
# Default branch is resolved dynamically via `git symbolic-ref refs/remotes/origin/HEAD`;
# falls back to `origin/main` when the remote HEAD is not set (same as the block message).
#
# Marker mechanics: single-use, TTL 5 min, consumed on use — every subsequent push /
# MR-create needs a fresh critic pass and a new verdict file.

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

# Portable sha256: prefer sha256sum (Linux/GNU), fall back to shasum -a 256 (macOS).
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print $1}'
  else
    shasum -a 256 | awk '{print $1}'
  fi
}

# Resolve default branch dynamically; fall back to origin/main.
DEFAULT_REF="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/||' || echo "origin/main")"

# If there is no marker file at all — fall through to block.
if [[ ! -f "$MARKER" ]]; then
  :  # fall through
else
  NOW=$(date +%s)
  MTIME=$(stat -c %Y "$MARKER" 2>/dev/null || stat -f %m "$MARKER" 2>/dev/null || echo "$NOW")
  AGE=$(( NOW - MTIME ))

  # Always consume the marker (single-use), whether we pass or block.
  MARKER_CONTENT="$(cat "$MARKER")"
  rm -f "$MARKER"

  if [[ "$AGE" -gt 300 ]]; then
    # Stale marker; fall through to block with a note.
    cat >&2 <<EOF
auto-critic: verdict file expired (age ${AGE}s > 300s TTL). Run a fresh critic pass and write a new verdict file.
EOF
    exit 2
  fi

  # Empty / bare touch → reject with new-contract message.
  if [[ -z "$MARKER_CONTENT" ]] || ! printf '%s' "$MARKER_CONTENT" | grep -q '.'; then
    cat >&2 <<'EOF'
auto-critic: the verdict file is empty. A bare `touch ~/.claude-critic-approved` no longer satisfies the gate.

Write the file with both required lines AFTER a real critic pass:
    verdict: approve
    diff-sha256: <output of: git diff origin/<default-branch>...HEAD | sha256sum | awk '{print $1}'>
EOF
    exit 2
  fi

  # Owner escape hatch — explicit and loud.
  if printf '%s' "$MARKER_CONTENT" | grep -q '^bypass: owner-accepted-risk$'; then
    cat >&2 <<'EOF'

========================================================================
auto-critic: AUDITED BYPASS — owner-accepted-risk was set in verdict file.
Hash check skipped. This bypass is intentional and carries owner risk.
Ensure an @critic review is completed at the next appropriate checkpoint.
========================================================================

EOF
    exit 0
  fi

  # Parse required fields.
  VERDICT_LINE="$(printf '%s' "$MARKER_CONTENT" | grep '^verdict: ' | head -1 || true)"
  SHA_LINE="$(printf '%s' "$MARKER_CONTENT" | grep '^diff-sha256: ' | head -1 || true)"

  if [[ -z "$VERDICT_LINE" ]] || [[ -z "$SHA_LINE" ]]; then
    cat >&2 <<'EOF'
auto-critic: verdict file is missing required fields. Both lines are required:
    verdict: approve
    diff-sha256: <sha256 of git diff origin/<default-branch>...HEAD>
EOF
    exit 2
  fi

  VERDICT="$(printf '%s' "$VERDICT_LINE" | sed 's/^verdict: //')"
  STORED_SHA="$(printf '%s' "$SHA_LINE" | sed 's/^diff-sha256: //')"

  if [[ "$VERDICT" != "approve" ]]; then
    cat >&2 <<EOF
auto-critic: verdict is '${VERDICT}', not 'approve'. Address the flagged items and run a fresh critic pass.
EOF
    exit 2
  fi

  # Recompute the diff sha256 now and compare.
  LIVE_SHA="$(git diff "${DEFAULT_REF}...HEAD" 2>/dev/null | sha256_of)"

  if [[ "$LIVE_SHA" != "$STORED_SHA" ]]; then
    cat >&2 <<EOF
auto-critic: diff-sha256 mismatch — the diff has changed since critic reviewed it.

  Stored: ${STORED_SHA}
  Current: ${LIVE_SHA}

Run a fresh critic pass on the current diff, then regenerate the verdict file:
  1. git diff ${DEFAULT_REF}...HEAD | sha256sum | awk '{print \$1}'
  2. Write ~/.claude-critic-approved with:
         verdict: approve
         diff-sha256: <hash from step 1>
EOF
    exit 2
  fi

  # All checks passed.
  exit 0
fi

# No marker file — emit the full instruction block.
LIVE_SHA_HINT="$(git diff "${DEFAULT_REF}...HEAD" 2>/dev/null | sha256_of || echo "<run: git diff ${DEFAULT_REF}...HEAD | sha256sum | awk '{print \$1}'>")"

cat >&2 <<EOF
auto-critic: a mandatory critic check is required before this mutation.

1. Invoke the critic sub-agent with:
   - for \`git push\` — the full branch diff (\`git diff ${DEFAULT_REF}...HEAD\`) plus the branch name and intended PR/MR summary;
   - for \`glab mr create\` — the MR title, description, and a diff summary.
   Include an \`<inherited-invariants>\` block (use \`scripts/role-invariants.sh critic\`) in the prompt.
   If the \`critic\` subagent_type from this plugin (\`neuro-matrix:critic\`) is not registered
   in the current environment, fall back to \`general-purpose\` with the body of \`agents/critic.md\`
   as the system-prompt template. The role contract is stable; the binding is not.

2. If critic returns \`approve\`, compute the diff sha256 and write the verdict file as a
   SEPARATE command before re-running the original command:

       DIFF_SHA=\$(git diff ${DEFAULT_REF}...HEAD | sha256sum | awk '{print \$1}')
       printf 'verdict: approve\ndiff-sha256: %s\n' "\$DIFF_SHA" > ~/.claude-critic-approved

   Then re-run the original command.

   Current diff sha256 (for reference): ${LIVE_SHA_HINT}

3. If critic returns \`fix-required\` — address the flagged items first, then loop again from step 1.

Owner bypass (risk accepted, audit trail required):
   printf 'bypass: owner-accepted-risk\n' > ~/.claude-critic-approved
   (A prominent warning will be emitted; the bypass is single-use and TTL-bound.)
EOF
exit 2
