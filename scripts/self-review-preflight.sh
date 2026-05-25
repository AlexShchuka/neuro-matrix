#!/usr/bin/env bash
# UserPromptSubmit hook: if the prompt explicitly asks for a critical review of
# an artifact (this plugin or any plugin / file), emit a reading-list reminder.
# Without this, the orchestrator skips artifact reading and slips into inverted
# sycophancy — see invariant #20 and README §3 rule 10.
#
# Detection: the prompt contains an explicit critical-review intent in Russian
# or English. Match → emit; no match → silent.
#
# Output: a <self-review-preflight> block on stdout; never blocks the prompt.

set -euo pipefail

PROMPT_JSON=$(cat)
PROMPT=$(printf '%s' "$PROMPT_JSON" | jq -r '.prompt // empty' 2>/dev/null || true)

if [[ -z "$PROMPT" ]]; then
  exit 0
fi

if ! printf '%s' "$PROMPT" | grep -qiE 'критически\s*оцен|критическ[а-яё]+\s*(обзор|ревью|оценк)|сделай\s+ревью|ещё\s+раз\s+(оцен|про(верь|гон))|review\s+(this|the|that)\s+(plugin|artifact|doc|md|design)|assess\s+(this|the|that)\s+(plugin|artifact|design|doc)|critically\s+(evaluate|assess|review)|re-review|review\s+again'; then
  exit 0
fi

cat <<'EOF'
<self-review-preflight>
You are being asked for a critical review of an artifact. Before producing critique, satisfy these gates:

1. READ the artifact's key files first. For a plugin under `${CLAUDE_PLUGIN_ROOT}` — at minimum:
   - README.md (overview, stated goals, roadmap)
   - CLAUDE.md (operating protocol)
   - invariants.txt (the invariants list)
   - eval/criteria.md (operational definitions of MET/UNMET)
   - eval/README.md (eval methodology, validity caveats)

2. Every negative claim — disagreement, weakness, "remaining gap" — must be paired with adjacent tool-output evidence in the same reply (invariants #1 and #20). If you find yourself listing weaknesses without adjacent file reads — STOP. That is inverted sycophancy, not rigor.

3. Counter-variant: would the same model, given the same artifact but without a critical-review prompt, list these as problems? If no — the critique is template-driven, not artifact-driven. Recompute from the artifact.

4. If the artifact's own §"validity caveats" / "roadmap" / "what's not here yet" already lists a gap — that is the author's self-acknowledgment, not your finding; do not repackage it as critique.
</self-review-preflight>
EOF
