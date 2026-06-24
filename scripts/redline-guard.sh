#!/usr/bin/env bash
# PreToolUse hook: deterministic redline guard (ROADMAP N6).
#
# Mechanically fences hard-prohibited git/k8s actions that prose and a
# low-probability sampler cannot reliably block.  Runs EARLY in the Bash
# PreToolUse chain — before auto-critic.sh — so no critic round-trip is
# possible after a match.
#
# Block set (exit 2 with named rule):
#   RULE force-push      : git push with --force / -f / --force-with-lease / +refspec
#   RULE skip-hooks      : git push with --no-verify or --no-gpg-sign
#   RULE merge-onto-main : git merge/rebase when current branch IS main/master,
#                          OR when main/master is an explicit argument
#   RULE pr-mr-mutate    : gh pr merge|close|delete / glab mr merge|close|delete
#   RULE k8s-mutate      : kubectl apply|delete|edit|patch|scale|replace|rollout
#   RULE helm-mutate     : helm install|upgrade|uninstall|rollback
#
# Allow (exit 0):
#   plain git push (incl. to main — owner-solo-private-repo delegation lifts it)
#   read-only kubectl: get|describe|logs|events
#   read-only helm: list|status|get
#   everything else
#
# Fail-SAFE contract:
#   - Exit 2 only on a POSITIVE redline match.
#   - If jq is unavailable or stdin is malformed → exit 0 (fail-open, not crash-block).
#   - Only Bash tool calls are inspected; all others pass immediately.
#
# Bash-3.2 compatible (no mapfile, no declare -A, no bash-4+ features).

set -euo pipefail

INPUT="$(cat)"

# Guard: only process Bash tool calls.
TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")"
[[ "$TOOL_NAME" == "Bash" ]] || exit 0

COMMAND="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")"
[[ -n "$COMMAND" ]] || exit 0

# ── Helpers ──────────────────────────────────────────────────────────────────

# cmd_contains_token TOKEN: true when TOKEN appears as a word or flag in COMMAND,
# after stripping leading env-var assignments (FOO=bar VAR=baz cmd ...).
# Uses grep -E; bash-3.2 compatible.
cmd_has_token() {
  local token="$1"
  # Anchor: token must be preceded by start-of-string, space, semicolon,
  # ampersand, pipe, or opening paren — not embedded inside a word.
  printf '%s' "$COMMAND" | grep -qE "(^|[[:space:];&|(])${token}([[:space:]]|\$)"
}

# cmd_has_git_subcommand SUBCMD: true when the command contains
# `git [options] SUBCMD` possibly preceded by env vars or `git -C <path>`.
# Handles: git push, git -C /some/path push, GIT_DIR=x git push, etc.
cmd_has_git_subcommand() {
  local sub="$1"
  printf '%s' "$COMMAND" | grep -qE "(^|[[:space:];&|(])(([A-Za-z_][A-Za-z_0-9]*=[^[:space:]]+ )*git[[:space:]]+(-[^[:space:]]+ [^[:space:]]+ )*${sub})([[:space:]]|\$)"
}

# cmd_has_git_push: true when command contains a git push invocation.
cmd_has_git_push() {
  cmd_has_git_subcommand "push"
}

# ── RULE: force-push ──────────────────────────────────────────────────────────
# Block git push --force / -f / --force-with-lease / +<refspec>
if cmd_has_git_push; then
  # Check for --force or --force-with-lease
  if printf '%s' "$COMMAND" | grep -qE '[[:space:]]--force(|-with-lease)(=[^[:space:]]*)?([[:space:]]|$)'; then
    cat >&2 <<'EOF'
redline-guard: BLOCK [force-push]
  git push with --force or --force-with-lease is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — "--force push" is forbidden.
  Remove the --force / --force-with-lease flag and re-evaluate.
EOF
    exit 2
  fi

  # Check for -f flag (short form, possibly in a cluster like -fu, but -f alone or leading)
  # Match: -f as standalone flag or as part of a short-flag cluster containing f
  # Do NOT match --force again (already caught above).
  if printf '%s' "$COMMAND" | grep -qE '[[:space:]]-[a-eg-zA-Z]*f[a-zA-Z]*([[:space:]]|$)'; then
    cat >&2 <<'EOF'
redline-guard: BLOCK [force-push]
  git push with -f (short force flag) is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — "--force push" is forbidden.
  Remove the -f flag and re-evaluate.
EOF
    exit 2
  fi

  # Check for +<refspec> (force-push individual ref)
  # Matches tokens like +HEAD:refs/heads/main, +main, +origin/main:main, etc.
  # A '+' at the start of a refspec argument (preceded by space or start).
  if printf '%s' "$COMMAND" | grep -qE '[[:space:]]\+[^[:space:]-][^[:space:]]*([[:space:]]|$)'; then
    cat >&2 <<'EOF'
redline-guard: BLOCK [force-push]
  git push with a force-prefixed refspec (+<src>:<dst>) is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — "--force push" is forbidden.
  Remove the + refspec prefix and re-evaluate.
EOF
    exit 2
  fi
fi

# ── RULE: skip-hooks ──────────────────────────────────────────────────────────
# Block git push --no-verify or --no-gpg-sign
if cmd_has_git_push; then
  if printf '%s' "$COMMAND" | grep -qE '[[:space:]]--(no-verify|no-gpg-sign)([[:space:]]|$)'; then
    cat >&2 <<'EOF'
redline-guard: BLOCK [skip-hooks]
  git push with --no-verify or --no-gpg-sign is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — skipping git hooks is forbidden.
  Remove the flag and re-evaluate.
EOF
    exit 2
  fi
fi

# ── RULE: merge-onto-main ────────────────────────────────────────────────────
# Block: git merge ... when current branch is main/master
#        git rebase ... when current branch is main/master
#        git merge main|master (explicit arg)
#        git rebase main|master (explicit arg)
if cmd_has_git_subcommand "merge" || cmd_has_git_subcommand "rebase"; then
  # Check if main/master is an explicit argument to merge/rebase.
  if printf '%s' "$COMMAND" | grep -qE '[[:space:]](main|master)([[:space:]]|$)'; then
    cat >&2 <<'EOF'
redline-guard: BLOCK [merge-onto-main]
  git merge/rebase with main or master as an explicit argument is prohibited.
  Rule: CLAUDE.md § Hard prohibitions — "merge or rebase onto main locally" is forbidden.
  Use a feature branch and open a PR/MR instead.
EOF
    exit 2
  fi

  # Check if current branch is main or master.
  # Only attempt if inside a git work tree; if not, skip this sub-check safely.
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || echo "")"
    if [[ "$CURRENT_BRANCH" == "main" || "$CURRENT_BRANCH" == "master" ]]; then
      cat >&2 <<'EOF'
redline-guard: BLOCK [merge-onto-main]
  git merge/rebase is prohibited while on main or master branch.
  Rule: CLAUDE.md § Hard prohibitions — "merge or rebase onto main locally" is forbidden.
  Switch to a feature branch first.
EOF
      exit 2
    fi
  fi
fi

# ── RULE: pr-mr-mutate ───────────────────────────────────────────────────────
# Block: gh pr merge|close|delete  /  glab mr merge|close|delete
if printf '%s' "$COMMAND" | grep -qE "(^|[[:space:];&|(])gh[[:space:]]+pr[[:space:]]+(merge|close|delete)([[:space:]]|\$)"; then
  cat >&2 <<'EOF'
redline-guard: BLOCK [pr-mr-mutate]
  gh pr merge/close/delete is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — "merge or approve MRs / PRs; close or delete MRs / PRs" is forbidden.
  Ask the human owner to perform this operation directly.
EOF
  exit 2
fi

if printf '%s' "$COMMAND" | grep -qE "(^|[[:space:];&|(])glab[[:space:]]+mr[[:space:]]+(merge|close|delete)([[:space:]]|\$)"; then
  cat >&2 <<'EOF'
redline-guard: BLOCK [pr-mr-mutate]
  glab mr merge/close/delete is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — "merge or approve MRs / PRs; close or delete MRs / PRs" is forbidden.
  Ask the human owner to perform this operation directly.
EOF
  exit 2
fi

# ── RULE: k8s-mutate ─────────────────────────────────────────────────────────
# Block: kubectl apply|delete|edit|patch|scale|replace|rollout
# Allow: kubectl get|describe|logs|events (read-only)
if printf '%s' "$COMMAND" | grep -qE "(^|[[:space:];&|(])kubectl[[:space:]]+(apply|delete|edit|patch|scale|replace|rollout)([[:space:]]|\$)"; then
  cat >&2 <<'EOF'
redline-guard: BLOCK [k8s-mutate]
  kubectl apply/delete/edit/patch/scale/replace/rollout is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — mutating production k8s state is forbidden.
  Only read-only operations (get, describe, logs, events) are permitted.
EOF
  exit 2
fi

# ── RULE: helm-mutate ────────────────────────────────────────────────────────
# Block: helm install|upgrade|uninstall|rollback
# Allow: helm list|status|get (read-only)
if printf '%s' "$COMMAND" | grep -qE "(^|[[:space:];&|(])helm[[:space:]]+(install|upgrade|uninstall|rollback)([[:space:]]|\$)"; then
  cat >&2 <<'EOF'
redline-guard: BLOCK [helm-mutate]
  helm install/upgrade/uninstall/rollback is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — mutating production k8s state is forbidden.
  Only read-only operations (list, status, get) are permitted.
EOF
  exit 2
fi

# ── No redline matched — allow ────────────────────────────────────────────────
exit 0
