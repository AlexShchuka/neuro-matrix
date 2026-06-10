#!/usr/bin/env bash
# Print the invariants from invariants.txt most relevant to a given sub-agent role.
# Used by the orchestrator to populate `<inherited-invariants>` blocks in sub-agent prompts —
# sub-agents do not receive the UserPromptSubmit hook, so the invariant self-check has to
# travel with the prompt, explicitly.
#
# Selection: information-bottleneck — minimum subset covering the role's typical failure modes.
# Invariants are addressed by stable "#N" id (grep "^#N "), never by file line.
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
# Output: the role's inherited invariant subset (one line per id listed below), suitable for
# pasting into a sub-agent prompt under `<inherited-invariants>` ... `</inherited-invariants>`.

set -euo pipefail

ROLE="${1:-}"
# Plugin root: CLAUDE_PLUGIN_ROOT overrides; otherwise self-resolve from this script's location (#19).
ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
INVARIANTS="${ROOT}/invariants.txt"
if [[ ! -f "$INVARIANTS" ]]; then
  echo "invariants.txt not found at $INVARIANTS (root = CLAUDE_PLUGIN_ROOT override or self-resolved)" >&2
  exit 1
fi

KNOWN_ROLES="developer analyzer critic epistemic-auditor"
role_invariants() {
  case "$1" in
    developer)         echo "1 2 4 14 19 20 22" ;;
    analyzer)          echo "1 12 13 19 20 22" ;;
    critic)            echo "3 6 9 19 20 22" ;;
    epistemic-auditor) echo "6 16 17 19 20 22" ;;
    *)                 return 1 ;;
  esac
}
# #19 (own-interest / anti-sycophancy) is universal: every sub-agent can be pressured by
# the orchestrator to silently capitulate. Propagating it to every role closes that loophole.
# #20 (anti-inverted-sycophancy) is the mirror: under critical-review prompts the agent
# may over-disagree to look independent; same universal propagation closes that mirror loophole.
# #22 (no-opinion-before-depth) is the strongest gate: on any unread artifact the only
# permitted output is questions, neutral summary, or "not yet read enough". Universal because
# every role can be handed an unread artifact and asked for a take.
# #14 (greenfield code-absence) goes to developer specifically: code-absence on a
# new-feature spec is the work to do, not a reason to declare out-of-scope.

if ! IDS="$(role_invariants "$ROLE")"; then
  echo "Unknown role: $ROLE. Known: $KNOWN_ROLES" >&2
  exit 1
fi

status=0
for n in $IDS; do
  if ! grep -m1 -E "^#${n}[[:space:]]" "$INVARIANTS"; then
    echo "role-invariants: invariant #${n} not found in $INVARIANTS" >&2
    status=1
  fi
done
exit "$status"
