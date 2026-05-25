#!/usr/bin/env bash
# Print the invariants from invariants.txt most relevant to a given sub-agent role.
# Used by the orchestrator to populate `<inherited-invariants>` blocks in sub-agent prompts —
# sub-agents do not receive the UserPromptSubmit hook, so the invariant self-check has to
# travel with the prompt, explicitly.
#
# Selection: information-bottleneck — minimum subset whose semantic span covers the role's
# typical failure modes (not the full pool of ~22). Indices are 1-based line numbers in invariants.txt.
#
# Roles:
#   developer         — mutation gate, no-invention, evidence-paired claims
#   analyzer          — search-before-ask, mental-model gate, evidence-paired claims
#   critic            — scope discipline, decoration / neuroslop shape, associative-marker
#   epistemic-auditor — associative-marker, developer-side ambiguity, cross-turn contradiction
#
# Usage:
#   scripts/role-invariants.sh <role>
#
# Output: 3 invariant lines, suitable for pasting into a sub-agent prompt under
# `<inherited-invariants>` ... `</inherited-invariants>`.

set -euo pipefail

ROLE="${1:-}"
INVARIANTS="${CLAUDE_PLUGIN_ROOT:-}/invariants.txt"
if [[ ! -f "$INVARIANTS" ]]; then
  echo "invariants.txt not found at $INVARIANTS (set CLAUDE_PLUGIN_ROOT)" >&2
  exit 1
fi

declare -A ROLE_LINES=(
  [developer]="1 2 4 14 19 20 22"
  [analyzer]="1 12 13 19 20 22"
  [critic]="3 6 9 19 20 22"
  [epistemic-auditor]="6 16 17 19 20 22"
)
# Line 19 (own-interest / anti-sycophancy) is universal: every sub-agent can be pressured by
# the orchestrator to silently capitulate. Propagating it to every role closes that loophole.
# Line 20 (anti-inverted-sycophancy) is the mirror: under critical-review prompts the agent
# may over-disagree to look independent; same universal propagation closes that mirror loophole.
# Line 22 (no-opinion-before-depth) is the strongest gate: on any unread artifact the only
# permitted output is questions, neutral summary, or "not yet read enough". Universal because
# every role can be handed an unread artifact and asked for a take.
# Line 14 (greenfield code-absence) goes to developer specifically: code-absence on a
# new-feature spec is the work to do, not a reason to declare out-of-scope.

LINES="${ROLE_LINES[$ROLE]:-}"
if [[ -z "$LINES" ]]; then
  echo "Unknown role: $ROLE. Known: ${!ROLE_LINES[*]}" >&2
  exit 1
fi

for n in $LINES; do
  sed -n "${n}p" "$INVARIANTS"
done
