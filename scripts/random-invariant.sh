#!/usr/bin/env bash
# UserPromptSubmit hook: samples one invariant from invariants.txt and emits it as a
# self-check anchor for the upcoming reply. Two-axis annotation:
#   - risk class [critical|important|style] drives weighted sampling 3/2/1.
#   - deontic modality [O|P|F] (obligation/permission/forbidden), when present after the
#     risk tag, is surfaced in the self-check block so the agent applies the right kind
#     of duty (must-do vs context-dependent vs must-not-do).

set -euo pipefail

INVARIANTS="${CLAUDE_PLUGIN_ROOT}/invariants.txt"

if [[ ! -f "$INVARIANTS" ]]; then
  exit 0
fi

risk_weight() {
  case "$1" in
    critical) echo 3 ;;
    important) echo 2 ;;
    *) echo 1 ;;
  esac
}
deontic_name() {
  case "$1" in
    O) echo "obligation" ;;
    P) echo "permission" ;;
    F) echo "forbidden" ;;
    *) echo "" ;;
  esac
}
deontic_note() {
  case "$1" in
    O) echo "applying is required; not applying is a defect" ;;
    P) echo "context-dependent; default to applying, deviate with explicit reason" ;;
    F) echo "doing the action is a defect" ;;
    *) echo "" ;;
  esac
}
declare -a LINES DEONTICS WEIGHTS
total=0
ln=0

while IFS= read -r line; do
  ln=$((ln + 1))
  [[ -z "$line" ]] && continue
  [[ "$line" =~ ^[[:space:]]*#[[:space:]] ]] && continue
  body="$line"
  [[ "$body" =~ ^#[0-9]+[[:space:]]+(.*)$ ]] && body="${BASH_REMATCH[1]}"
  deontic=""
  if [[ "$body" =~ ^\[([a-z]+)\][[:space:]]+\[([OPF])\] ]]; then
    risk="${BASH_REMATCH[1]}"
    deontic="${BASH_REMATCH[2]}"
    w="$(risk_weight "$risk")"
  elif [[ "$body" =~ ^\[([a-z]+)\] ]]; then
    risk="${BASH_REMATCH[1]}"
    w="$(risk_weight "$risk")"
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
  printf 'random-invariant: warning: no invariants parsed from %s — self-check skipped this turn; check the file format.\n' "$INVARIANTS" >&2
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

# --- Forensic trace + abort trap (#21) ----------------------------------------
# One trace line per emit attempt. On the next malformed self-check block this
# discriminates the surviving hypotheses: trace OK + no ABORT record = payload was
# correct at emit time (post-script transit mangling); trace OK + ABORT = the final
# cat was cut mid-emit (read end closed early); no trace = died before emitting.
# Trace writes must never break the hook — every path ends in `|| true`.
TRACE="${HOME}/.claude-invariant-last"
if [[ -f "$TRACE" && "$(wc -c < "$TRACE" 2>/dev/null || echo 0)" -gt 102400 ]]; then
  { tail -n 100 "$TRACE" > "${TRACE}.tmp" && mv "${TRACE}.tmp" "$TRACE"; } 2>/dev/null || true
fi
FILE_SHA="$( { md5sum "$INVARIANTS" 2>/dev/null || md5 -q "$INVARIANTS" 2>/dev/null; } | cut -d' ' -f1 || true )"
printf '%s\tpick=%s\tsha=%s\tline=%.40s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$pick" "${FILE_SHA:-?}" "$LINE" \
  >> "$TRACE" 2>/dev/null || true
ABORTED=0
trap '[ "$ABORTED" -eq 1 ] || { ABORTED=1; printf "%s\tABORT\tpick=%s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${pick:-?}" >> "$TRACE" 2>/dev/null; }; true' ERR PIPE
# -------------------------------------------------------------------------------

deontic_text=""
if [[ -n "$DEONTIC" ]]; then
  name="$(deontic_name "$DEONTIC")"
  note="$(deontic_note "$DEONTIC")"
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
