#!/usr/bin/env bash
# PreToolUse hook: non-blocking skill-consult nudge for Agent spawns.
#
# When an Agent tool is about to be spawned, checks whether the spawn's
# description (or prompt) contains a keyword matching any skill registered
# in skills/*/SKILL.md.  On a match it prints ONE stderr reminder and exits 0.
# The hook ALWAYS exits 0 — skills are optional; this is a nudge, not a gate.
#
# Skill list is derived AT RUNTIME from skills/*/SKILL.md `name:` frontmatter
# so it never drifts from the actual skill set (drift-resistance is the point).
#
# Rationale (N10): text guidance erodes under load.  A deterministic pre-spawn
# nudge is a mechanical backstop for the N9 "no skill-consult" defect class.

set -euo pipefail

INPUT="$(cat)"

# Act only on Agent tool spawns.
TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")"
[[ "$TOOL_NAME" == "Agent" ]] || exit 0

# Extract description and prompt from tool_input; combine for matching.
DESCRIPTION="$(printf '%s' "$INPUT" | jq -r '.tool_input.description // ""' 2>/dev/null || echo "")"
PROMPT="$(printf '%s' "$INPUT" | jq -r '.tool_input.prompt // ""' 2>/dev/null || echo "")"
HAYSTACK="$(printf '%s\n%s' "$DESCRIPTION" "$PROMPT" | tr '[:upper:]' '[:lower:]')"

# Locate the plugin root: resolve from this script's own directory.
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${_SCRIPT_DIR}/.." && pwd)"
SKILLS_DIR="${PLUGIN_ROOT}/skills"

[[ -d "$SKILLS_DIR" ]] || exit 0

# Collect skill names from SKILL.md `name:` frontmatter at runtime.
MATCHED_SKILL=""
while IFS= read -r skill_file; do
  # Parse the `name:` line from YAML frontmatter (first occurrence).
  skill_name="$(grep -m1 '^name:' "$skill_file" | sed 's/^name:[[:space:]]*//' | tr -d '\r' || true)"
  [[ -n "$skill_name" ]] || continue

  # Derive keywords from the skill name: split on hyphens, use full name and each word.
  # This keeps matching conservative (whole-word substrings only, not arbitrary fragments).
  keywords=("$skill_name")
  IFS='-' read -ra parts <<< "$skill_name"
  for part in "${parts[@]}"; do
    [[ ${#part} -ge 4 ]] && keywords+=("$part")
  done

  for kw in "${keywords[@]}"; do
    if printf '%s' "$HAYSTACK" | grep -qiwE "$kw"; then
      MATCHED_SKILL="$skill_name"
      break 2
    fi
  done
done < <(find "$SKILLS_DIR" -maxdepth 2 -name "SKILL.md" | sort)

if [[ -n "$MATCHED_SKILL" ]]; then
  printf 'skill-consult: description may match skill %s — consider Skill(%s) before a bespoke agent\n' \
    "$MATCHED_SKILL" "$MATCHED_SKILL" >&2
fi

exit 0
