#!/usr/bin/env bash
# protocol-paths.sh — sourced helper: defines protocol_path_matches().
#
# A "protocol artifact" is any file whose path matches the set below.
# These paths are the enforcement layer for this co-system; changes to them
# require human approval before push (see auto-critic.sh § Human gate).
#
# Protocol-path set (prefix/glob match, bash case-pattern):
#   invariants.txt, CLAUDE.md          — top-level config/invariant files
#   agents/                            — agent role definitions
#   hooks/                             — hook configs
#   eval/                              — evaluation probes
#   references/protocol/               — protocol docs
#   scripts/                           — runtime enforcement scripts
#
# Usage: source this file, then call:
#   protocol_path_matches "<relative-path>"  → returns 0 (match) or 1 (no match)

protocol_path_matches() {
  local p="$1"
  case "$p" in
    invariants.txt|CLAUDE.md) return 0 ;;
    agents/*|hooks/*|eval/*|references/protocol/*|scripts/*) return 0 ;;
  esac
  return 1
}
