#!/usr/bin/env bash
# UserPromptSubmit hook: samples one invariant from invariants.txt and emits it as a
# self-check anchor for the upcoming reply. Two-axis annotation:
#   - risk class [critical|important|style] drives weighted sampling 3/2/1.
#   - deontic modality [O|P|F] (obligation/permission/forbidden), when present after the
#     risk tag, is surfaced in the self-check block so the agent applies the right kind
#     of duty (must-do vs context-dependent vs must-not-do).
# Lines starting with `#` are treated as comments and skipped.

set -euo pipefail

INVARIANTS="${CLAUDE_PLUGIN_ROOT}/invariants.txt"

if [[ ! -f "$INVARIANTS" ]]; then
  exit 0
fi

declare -A W=([critical]=3 [important]=2 [style]=1)
declare -A DEONTIC_NAME=([O]="obligation" [P]="permission" [F]="forbidden")
declare -A DEONTIC_NOTE=(
  [O]="applying is required; not applying is a defect"
  [P]="context-dependent; default to applying, deviate with explicit reason"
  [F]="doing the action is a defect"
)
declare -a LINES DEONTICS WEIGHTS
total=0
ln=0

while IFS= read -r line; do
  ln=$((ln + 1))
  [[ -z "$line" ]] && continue
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  deontic=""
  if [[ "$line" =~ ^\[([a-z]+)\][[:space:]]+\[([OPF])\] ]]; then
    risk="${BASH_REMATCH[1]}"
    deontic="${BASH_REMATCH[2]}"
    w="${W[$risk]:-1}"
  elif [[ "$line" =~ ^\[([a-z]+)\] ]]; then
    risk="${BASH_REMATCH[1]}"
    w="${W[$risk]:-1}"
  else
    w=1
    printf 'random-invariant: warning: untagged line %d sampled at style-weight (fallback); add [critical|important|style] prefix\n' "$ln" >&2
  fi
  LINES+=("$line")
  DEONTICS+=("$deontic")
  WEIGHTS+=("$w")
  total=$((total + w))
done < "$INVARIANTS"

if [[ "$total" -eq 0 ]]; then
  exit 0
fi

pick=$(( (RANDOM * 32768 + RANDOM) % total ))
sum=0
LINE=""
DEONTIC=""
for i in "${!WEIGHTS[@]}"; do
  sum=$((sum + WEIGHTS[i]))
  if [[ "$pick" -lt "$sum" ]]; then
    LINE="${LINES[$i]}"
    DEONTIC="${DEONTICS[$i]}"
    break
  fi
done

if [[ -z "$LINE" ]]; then
  exit 0
fi

deontic_text=""
if [[ -n "$DEONTIC" ]]; then
  name="${DEONTIC_NAME[$DEONTIC]:-}"
  note="${DEONTIC_NOTE[$DEONTIC]:-}"
  deontic_text="This invariant's deontic class: ${DEONTIC} (${name}) — ${note}."
fi

cat <<EOF
<self-check-invariant>
For this turn, run an explicit self-check against this risk-weighted sampled invariant (critical ×3, important ×2, style ×1; deontic O = obligation, P = permission, F = forbidden):
${deontic_text:+
${deontic_text}
}
> ${LINE}

Before sending your reply, verify it does not violate this invariant. If it does, fix the draft. If you cannot satisfy it, halt and ask.
</self-check-invariant>
EOF
