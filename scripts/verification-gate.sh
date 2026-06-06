#!/usr/bin/env bash
# PreToolUse hook: the VERIFICATION half of an EviBound-style dual gate.
#
# `auto-critic.sh` is the Approval Gate — it blocks a `git commit` until @critic
# semantically approves the proposed output. Approval is necessary but NOT
# sufficient: EviBound (arXiv:2511.05524) shows prompt/approval-only governance
# leaves ~100% false-completion, a verification-only gate ~25%, and only the dual
# gate reaches 0%. "Verify before you commit" (SAVeR, arXiv:2604.08401).
#
# This script is that post-execution Verification Gate. On `git commit` it runs
# machine-checkable evidence on the artifacts about to land and blocks (exit 2)
# the commit if any fails:
#   - *.sh   → `bash -n`        (shell syntax)
#   - *.py   → `ast.parse`      (Python syntax)
#   - *.json → `jq empty`       (JSON validity)
#
# Scope: the commit boundary only (not `glab mr create` / `gh pr create` — by then
# the artifacts are already committed; the gate must fire before they land).
#
# Self-contained: unlike the approval gate it needs no marker and no agent
# round-trip — it produces the evidence itself. Tooling-absence never blocks
# (graceful degradation, matching cycle-detector's "never block on parser
# failure" stance) — a missing checker means that file-type is skipped, not failed.
#
# Source of files checked: the working tree at the file paths reported by
# `git diff --staged` (plus `git diff` when `-a`/`--all` is used). Working tree
# == what lands for the normal `git add && git commit` flow; partial-staging
# (`git add -p`) is a known blind spot and is out of scope for this gate.

set -euo pipefail

INPUT="$(cat)"

TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")"
[[ "$TOOL_NAME" == "Bash" ]] || exit 0

COMMAND="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")"
[[ -n "$COMMAND" ]] || exit 0

# Fire on `git commit` only.
printf '%s' "$COMMAND" | grep -qE '(^|[[:space:];&|(])git[[:space:]]+commit([[:space:]]|$)' || exit 0

# Must be inside a work tree to have anything to verify.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# Collect candidate files: staged adds/copies/modifies, plus unstaged tracked
# changes when the commit auto-stages them (`-a` / `--all`).
FILES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && FILES+=("$line")
done < <(git diff --staged --name-only --diff-filter=ACM 2>/dev/null)
# Detect auto-stage: standalone `--all`, or any short-flag cluster containing `a`
# (`-a`, `-am`, `-av`, `-amend` is NOT this — it is the long `--amend`, correctly excluded).
if printf '%s' "$COMMAND" | grep -qE '(^|[[:space:]])(--all|-[a-zA-Z]*a[a-zA-Z]*)([[:space:]]|$)'; then
  while IFS= read -r line; do
    [[ -n "$line" ]] && FILES+=("$line")
  done < <(git diff --name-only --diff-filter=ACM 2>/dev/null)
fi

[[ "${#FILES[@]}" -gt 0 ]] || exit 0

DEDUPED=()
while IFS= read -r line; do
  [[ -n "$line" ]] && DEDUPED+=("$line")
done < <(printf '%s\n' "${FILES[@]}" | sort -u)

FAILURES=()

for f in "${DEDUPED[@]}"; do
  [[ -f "$f" ]] || continue

  case "$f" in
    *.sh)
      if command -v bash >/dev/null 2>&1; then
        if ! err=$(bash -n "$f" 2>&1); then
          FAILURES+=("$f (shell syntax): ${err}")
        fi
      fi
      ;;
    *.py)
      if command -v python3 >/dev/null 2>&1; then
        if ! err=$(python3 -c 'import sys,ast; ast.parse(open(sys.argv[1]).read(), sys.argv[1])' "$f" 2>&1); then
          FAILURES+=("$f (python syntax): $(printf '%s' "$err" | tail -n 1)")
        fi
      fi
      ;;
    *.json)
      if command -v jq >/dev/null 2>&1; then
        if ! err=$(jq empty "$f" 2>&1); then
          FAILURES+=("$f (json validity): ${err}")
        fi
      fi
      ;;
  esac
done

[[ "${#FAILURES[@]}" -eq 0 ]] && exit 0

{
  echo "verification-gate: machine-checkable verification FAILED on staged artifacts — commit blocked."
  echo "Approval (critic) is necessary but not sufficient; the artifact's own evidence must pass first."
  echo
  for fail in "${FAILURES[@]}"; do
    echo "  - ${fail}"
  done
  echo
  echo "Fix the artifact(s) above, re-stage, and retry the commit. Do not bypass by claiming success —"
  echo "a coherent claim of completion is not a verified one (SAVeR, arXiv:2604.08401)."
} >&2
exit 2
