#!/usr/bin/env bash
# PreToolUse hook: deterministic redline guard (ROADMAP N6).
#
# Mechanically fences hard-prohibited git/k8s actions that prose and a
# low-probability sampler cannot reliably block.  Runs EARLY in the Bash
# PreToolUse chain — before auto-critic.sh — so no critic round-trip is
# possible after a match.
#
# ── THREAT MODEL & KNOWN LIMITATIONS ────────────────────────────────────────
#
# WHAT THIS GUARD STOPS (accidental / careless violations):
#   - Every force-push spelling: --force, -f, --force-with-lease, +<refspec>
#   - git push with --no-verify or --no-gpg-sign
#   - git merge / rebase onto main/master (by name or full refname)
#   - PR/MR merge, close, or delete via gh/glab CLI
#   - Production k8s mutations via kubectl / helm
#   - All of the above even through common wrappers: /usr/bin/git, ./git,
#     `command git`, `builtin git`, `exec git`, git global flags (--no-pager,
#     --bare, -C <path>, etc.), env-var prefixes (GIT_DIR=x git push ...)
#
# WHAT THIS GUARD IS NOT (accepted, out of scope):
#   This is defense-in-depth, NOT a sandbox.  A DELIBERATE caller can bypass
#   ANY PreToolUse regex guard — these are explicitly accepted and out of scope:
#
#   1. Command substitution / backticks:
#        $(echo git) push --force
#        `which git` push --force
#      The hook sees the literal string; it cannot evaluate shell expansions.
#
#   2. Configured git aliases:
#        git fpush   (where [alias] fpush = push --force)
#      The hook does not read ~/.gitconfig; it sees `git fpush`, not `push --force`.
#
#   3. Write-a-script-and-run:
#        printf '#!/bin/sh\ngit push --force\n' > /tmp/x.sh && bash /tmp/x.sh
#      The hook fires on the Write tool too, but cannot evaluate what the
#      script will do when later executed.
#
#   4. PATH manipulation:
#        PATH=/tmp:$PATH git push --force  (where /tmp/git is a wrapper)
#
#   Chasing these vectors in a regex hook is a losing arms race.  The correct
#   backstop for deliberate bypass is the human gate and the co-system trust
#   model (CLAUDE.md § Co-system contract), not pattern matching.
#
# ── Block set (exit 2 with named rule) ──────────────────────────────────────
#   RULE force-push      : git push with --force / -f / --force-with-lease / +refspec
#   RULE skip-hooks      : git push with --no-verify or --no-gpg-sign
#   RULE merge-onto-main : git merge/rebase when current branch IS main/master
#                          (including detached HEAD pointing at main/master commit),
#                          OR when main/master appears as an explicit argument
#                          (bare token OR full refname: refs/heads/main, heads/main)
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
# Design — chained-command handling:
#   The full COMMAND string is split on shell operators (&& || ; | ( )) into
#   segments.  EVERY segment is inspected independently.  Git subcommand detection
#   runs per-segment, not per-command, so `git status && git push --force` is
#   correctly caught in its second segment.
#
# Bash-3.2 compatible (no mapfile, no declare -A, no bash-4+ features).

set -euo pipefail

INPUT="$(cat)"

# Guard: only process Bash tool calls.
TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")"
[[ "$TOOL_NAME" == "Bash" ]] || exit 0

COMMAND="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")"
[[ -n "$COMMAND" ]] || exit 0

# ── Segment extractor ────────────────────────────────────────────────────────
# Split COMMAND on shell operators into independent segments, one per line.
# Operators: && || ; | ( )
# sed replaces each operator with a newline.
_segments="$(printf '%s' "$COMMAND" | sed 's/&&/\n/g; s/||/\n/g; s/;/\n/g; s/|/\n/g; s/(/\n/g; s/)/\n/g')"

# ── Git global value-taking options ──────────────────────────────────────────
# These consume the NEXT whitespace-separated token after the option.
# Used by the per-segment subcommand walker below.
_GIT_VALUE_OPTS="-C -c --git-dir --work-tree --namespace --super-prefix --exec-path"

# ── extract_git_invocation SEGMENT ────────────────────────────────────────────
# Walks the tokens of one segment, skipping:
#   - env-var assignments (FOO=bar)
#   - git global value-less options (--no-pager, --bare, -p, -P, etc.)
#   - git global value-taking options and their value token
# Prints "<subcmd> <rest-of-args>" to stdout, or nothing if no git found.
extract_git_invocation() {
  local seg="$1"
  local in_git=0
  local skip_next=0
  local subcommand=""
  local rest=""
  local token is_value_opt vopt

  for token in $seg; do
    # Consuming value of a global option.
    if [[ "$skip_next" -eq 1 ]]; then
      skip_next=0
      continue
    fi

    if [[ "$in_git" -eq 0 ]]; then
      # Skip env-var assignments before git (FOO=bar).
      printf '%s' "$token" | grep -qE '^[A-Za-z_][A-Za-z_0-9]*=' && continue
      # Skip shell built-in wrapper words that precede the git binary.
      # `command git`, `builtin git`, `exec git` — the wrapper is not git itself.
      if [[ "$token" == "command" || "$token" == "builtin" || "$token" == "exec" ]]; then
        continue
      fi
      # Match the git binary by BASENAME so /usr/bin/git, ./git, ../bin/git all fire.
      if [[ "$(basename "$token")" == "git" ]]; then
        in_git=1
      fi
      continue
    fi

    # Past `git` — check global options.

    # Value-less long options known to git-global.
    if printf '%s' "$token" | grep -qE '^--(no-pager|paginate|bare|no-replace-objects|literal-pathspecs|icase-pathspecs|no-optional-locks|list-cmds=.*)$'; then
      continue
    fi
    # Short value-less global flags: -p (paginate), -P (no-pager).
    if [[ "$token" == "-p" || "$token" == "-P" ]]; then
      continue
    fi

    # Value-taking global options (separate next token or =value attached).
    is_value_opt=0
    for vopt in $_GIT_VALUE_OPTS; do
      if [[ "$token" == "$vopt" ]]; then
        is_value_opt=1
        break
      fi
      if printf '%s' "$token" | grep -qE "^${vopt}="; then
        is_value_opt=2  # value is attached; no separate next token
        break
      fi
    done
    if [[ "$is_value_opt" -eq 1 ]]; then
      skip_next=1
      continue
    fi
    if [[ "$is_value_opt" -eq 2 ]]; then
      continue
    fi

    # First non-option token after `git` = subcommand.
    if [[ -z "$subcommand" ]]; then
      subcommand="$token"
      continue
    fi

    # Remainder = subcommand's own arguments.
    if [[ -n "$rest" ]]; then
      rest="$rest $token"
    else
      rest="$token"
    fi
  done

  if [[ -n "$subcommand" ]]; then
    printf '%s %s\n' "$subcommand" "$rest"
  fi
}

# ── check_segment SEGMENT ────────────────────────────────────────────────────
# Run all redline rules against a single command segment.
# Returns 0 (continue scanning) or calls exit 2 (block).
check_segment() {
  local seg="$1"

  # ── git rules (push / merge / rebase) ──────────────────────────────────────
  local git_info subcmd push_args merge_rebase_args
  git_info="$(extract_git_invocation "$seg")"
  subcmd="$(printf '%s' "$git_info" | awk '{print $1}')"
  local rest_args
  rest_args="$(printf '%s' "$git_info" | cut -s -d' ' -f2-)"

  case "$subcmd" in

    push)
      push_args="$rest_args"

      # RULE: force-push — --force / --force-with-lease
      # Scope: push args only.
      if printf '%s' " $push_args " | grep -qE ' --force(|-with-lease)(=[^[:space:]]*)?( |$)'; then
        cat >&2 <<'EOF'
redline-guard: BLOCK [force-push]
  git push with --force or --force-with-lease is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — "--force push" is forbidden.
  Remove the --force / --force-with-lease flag and re-evaluate.
EOF
        exit 2
      fi

      # RULE: force-push — -f short flag (or cluster containing f, e.g. -fu)
      # Scope: push args only (so `tar -xf` in a later segment does not fire).
      if printf '%s' " $push_args " | grep -qE ' -[a-eg-zA-Z]*f[a-zA-Z]*( |$)'; then
        cat >&2 <<'EOF'
redline-guard: BLOCK [force-push]
  git push with -f (short force flag) is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — "--force push" is forbidden.
  Remove the -f flag and re-evaluate.
EOF
        exit 2
      fi

      # RULE: force-push — +<refspec> (force-prefix on an individual ref)
      # Scope: push args only (so `echo +done` in a later segment does not fire).
      if printf '%s' " $push_args " | grep -qE ' \+[^[:space:]-][^[:space:]]*( |$)'; then
        cat >&2 <<'EOF'
redline-guard: BLOCK [force-push]
  git push with a force-prefixed refspec (+<src>:<dst>) is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — "--force push" is forbidden.
  Remove the + refspec prefix and re-evaluate.
EOF
        exit 2
      fi

      # RULE: skip-hooks — --no-verify / --no-gpg-sign
      # Scope: push args only.
      if printf '%s' " $push_args " | grep -qE ' --(no-verify|no-gpg-sign)( |$)'; then
        cat >&2 <<'EOF'
redline-guard: BLOCK [skip-hooks]
  git push with --no-verify or --no-gpg-sign is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — skipping git hooks is forbidden.
  Remove the flag and re-evaluate.
EOF
        exit 2
      fi
      ;;

    merge|rebase)
      merge_rebase_args="$rest_args"

      # RULE: merge-onto-main — main/master as an explicit positional argument.
      # Walk tokens, skipping known value-taking merge/rebase options.
      local skip_arg=0 found_main=0 arg
      for arg in $merge_rebase_args; do
        if [[ "$skip_arg" -eq 1 ]]; then
          skip_arg=0
          continue
        fi
        case "$arg" in
          --strategy|--strategy-option|-X|--onto|--gpg-sign|--exec|-x|-C)
            skip_arg=1; continue ;;
          --*) continue ;;   # other long options — not a positional arg
          -*) continue ;;    # short option cluster — not a positional arg
        esac
        # Positional argument: match by BASENAME so refs/heads/main, heads/main,
        # remotes/origin/master etc. are caught alongside the bare token.
        local _arg_base
        _arg_base="$(basename "$arg")"
        if [[ "$_arg_base" == "main" || "$_arg_base" == "master" ]]; then
          found_main=1; break
        fi
      done

      if [[ "$found_main" -eq 1 ]]; then
        cat >&2 <<'EOF'
redline-guard: BLOCK [merge-onto-main]
  git merge/rebase with main or master as an explicit argument is prohibited.
  Rule: CLAUDE.md § Hard prohibitions — "merge or rebase onto main locally" is forbidden.
  Use a feature branch and open a PR/MR instead.
EOF
        exit 2
      fi

      # RULE: merge-onto-main — current branch is main/master (incl. detached HEAD).
      # Only attempt when inside a git work tree; skip gracefully otherwise.
      if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        local cur_branch on_main=0
        cur_branch="$(git branch --show-current 2>/dev/null || echo "")"

        if [[ "$cur_branch" == "main" || "$cur_branch" == "master" ]]; then
          on_main=1
        fi

        # Detached-HEAD fallback: if branch name is empty, compare HEAD sha to
        # main and master.  If HEAD == main or HEAD == master → treat as on-main.
        if [[ -z "$cur_branch" && "$on_main" -eq 0 ]]; then
          local head_sha ref_sha ref
          head_sha="$(git rev-parse HEAD 2>/dev/null || echo "UNKNOWN")"
          for ref in main master; do
            ref_sha="$(git rev-parse "$ref" 2>/dev/null || echo "UNKNOWN")"
            if [[ "$head_sha" != "UNKNOWN" && "$ref_sha" != "UNKNOWN" \
                  && "$head_sha" == "$ref_sha" ]]; then
              on_main=1
              break
            fi
          done
        fi

        if [[ "$on_main" -eq 1 ]]; then
          cat >&2 <<'EOF'
redline-guard: BLOCK [merge-onto-main]
  git merge/rebase is prohibited while on main or master branch (including
  detached HEAD pointing at the main/master commit).
  Rule: CLAUDE.md § Hard prohibitions — "merge or rebase onto main locally" is forbidden.
  Switch to a feature branch first.
EOF
          exit 2
        fi
      fi
      ;;
  esac

  # ── PR/MR mutate rules (gh/glab) ───────────────────────────────────────────
  # These do not need git-subcommand parsing; match the segment directly.

  if printf '%s' "$seg" | grep -qE "(^|[[:space:];&|(])gh[[:space:]]+pr[[:space:]]+(merge|close|delete)([[:space:]]|\$)"; then
    cat >&2 <<'EOF'
redline-guard: BLOCK [pr-mr-mutate]
  gh pr merge/close/delete is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — "merge or approve MRs / PRs; close or delete MRs / PRs" is forbidden.
  Ask the human owner to perform this operation directly.
EOF
    exit 2
  fi

  if printf '%s' "$seg" | grep -qE "(^|[[:space:];&|(])glab[[:space:]]+mr[[:space:]]+(merge|close|delete)([[:space:]]|\$)"; then
    cat >&2 <<'EOF'
redline-guard: BLOCK [pr-mr-mutate]
  glab mr merge/close/delete is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — "merge or approve MRs / PRs; close or delete MRs / PRs" is forbidden.
  Ask the human owner to perform this operation directly.
EOF
    exit 2
  fi

  # ── k8s-mutate ──────────────────────────────────────────────────────────────
  if printf '%s' "$seg" | grep -qE "(^|[[:space:];&|(])kubectl[[:space:]]+(apply|delete|edit|patch|scale|replace|rollout)([[:space:]]|\$)"; then
    cat >&2 <<'EOF'
redline-guard: BLOCK [k8s-mutate]
  kubectl apply/delete/edit/patch/scale/replace/rollout is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — mutating production k8s state is forbidden.
  Only read-only operations (get, describe, logs, events) are permitted.
EOF
    exit 2
  fi

  # ── helm-mutate ─────────────────────────────────────────────────────────────
  if printf '%s' "$seg" | grep -qE "(^|[[:space:];&|(])helm[[:space:]]+(install|upgrade|uninstall|rollback)([[:space:]]|\$)"; then
    cat >&2 <<'EOF'
redline-guard: BLOCK [helm-mutate]
  helm install/upgrade/uninstall/rollback is unconditionally prohibited.
  Rule: CLAUDE.md § Hard prohibitions — mutating production k8s state is forbidden.
  Only read-only operations (list, status, get) are permitted.
EOF
    exit 2
  fi

  return 0
}

# ── Main: iterate over all segments ──────────────────────────────────────────
# Each segment is checked independently.  check_segment calls exit 2 on any
# redline match, which exits the whole script.  If all segments pass, exit 0.

while IFS= read -r _seg || [[ -n "$_seg" ]]; do
  # Skip blank segments.
  [[ -z "${_seg// /}" ]] && continue
  check_segment "$_seg"
done <<EOF
$_segments
EOF

# ── No redline matched — allow ────────────────────────────────────────────────
exit 0
