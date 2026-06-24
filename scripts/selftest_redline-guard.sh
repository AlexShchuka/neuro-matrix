#!/usr/bin/env bash
# selftest_redline-guard.sh — regression probe for scripts/redline-guard.sh
#
# Asserts:
#   BLOCK (exit 2) for adversarial bypass attempts (git global flags, detached HEAD,
#         path-to-git, command wrapper, full refname):
#     X01  git --no-pager push --force
#     X02  git --paginate push -f
#     X03  git --bare push --no-verify
#     X04  git --literal-pathspecs push --force
#     X05  git --no-pager merge main
#     X06  git --no-pager rebase master
#     X07  git status && git --no-pager push --force  (global flag in chain)
#     X08  git merge feature-branch on detached-HEAD-at-main  (bug 3 fix)
#     X11  /usr/bin/git push --force   (path-to-git bypass)
#     X12  command git push -f          (command wrapper bypass)
#     X13  git merge refs/heads/main    (full refname onto-main bypass)
#   ALLOW (exit 0) for false-block regression cases:
#     X09  git push origin feat && tar -xf a.tar  (tar -f must not trigger force-push)
#     X10  git push origin feat && echo +done     (+token in echo must not trigger refspec)
#
#   BLOCK (exit 2) for each hard-prohibited redline variant:
#     B01  git push --force
#     B02  git push -f
#     B03  git push --force-with-lease
#     B04  git push origin +HEAD:refs/heads/main  (force refspec)
#     B05  git push --no-verify
#     B06  git push --no-gpg-sign
#     B07  git merge main  (explicit main arg)
#     B08  git rebase main
#     B09  git merge master
#     B10  git rebase master
#     B11  gh pr merge 42
#     B12  gh pr close 42
#     B13  gh pr delete 42
#     B14  glab mr merge 7
#     B15  glab mr close 7
#     B16  glab mr delete 7
#     B17  kubectl apply -f deploy.yaml
#     B18  kubectl delete pod mypod
#     B19  kubectl edit deployment app
#     B20  kubectl patch svc mysvc
#     B21  kubectl scale deploy/app --replicas=3
#     B22  kubectl replace -f svc.yaml
#     B23  kubectl rollout restart deploy/app
#     B24  helm install myapp ./chart
#     B25  helm upgrade myapp ./chart
#     B26  helm uninstall myapp
#     B27  helm rollback myapp 1
#
#   ALLOW (exit 0) for permitted operations:
#     A01  git push origin feat-x
#     A02  git push origin main               (plain push to main is allowed via delegation)
#     A03  git push                            (bare push)
#     A04  git push -u origin main             (-u is not force)
#     A05  git commit -m "msg"
#     A06  ls
#     A07  kubectl get pods
#     A08  kubectl describe pod mypod
#     A09  kubectl logs mypod
#     A10  kubectl events
#     A11  helm list
#     A12  helm status myapp
#     A13  helm get values myapp
#     A14  git diff origin/main...HEAD
#     A15  echo "git push --force is bad"      (flag inside a string, non-git command)
#     A16  gh pr create --title "x"
#     A17  git push --tags                     (tags push, no force)
#     A18  glab mr create                      (create is not mutate/close/delete)
#
# Usage: bash scripts/selftest_redline-guard.sh
# Run from the repository root or any directory; paths are resolved relative
# to this script's own location.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/redline-guard.sh"

if [[ ! -f "$SCRIPT" ]]; then
  printf 'selftest: ERROR: script not found: %s\n' "$SCRIPT" >&2
  exit 1
fi

failures=0
pass=0

fail() {
  printf 'FAIL  %s\n' "$1"
  failures=$((failures + 1))
}

ok() {
  printf 'ok    %s\n' "$1"
  pass=$((pass + 1))
}

# ── Helpers ────────────────────────────────────────────────────────────────────

# make_json TOOL_NAME COMMAND → JSON payload matching PreToolUse hook stdin contract
make_json() {
  local tool_name="$1"
  local cmd="$2"
  # Use jq to safely encode the command string — avoids quoting edge-cases.
  jq -cn --arg tn "$tool_name" --arg cmd "$cmd" \
    '{"tool_name": $tn, "tool_input": {"command": $cmd}}'
}

# run_guard COMMAND → sets GUARD_EXIT, GUARD_STDERR
run_guard() {
  local cmd="$1"
  GUARD_EXIT=0
  GUARD_STDERR=""
  local json
  json="$(make_json "Bash" "$cmd")"
  GUARD_STDERR="$(printf '%s' "$json" | bash "$SCRIPT" 2>&1 1>/dev/null)" || GUARD_EXIT=$?
}

# assert_block LABEL COMMAND
assert_block() {
  local label="$1" cmd="$2"
  run_guard "$cmd"
  if [[ "$GUARD_EXIT" -eq 2 ]]; then
    ok "$label (blocked as required, exit 2)"
  else
    fail "$label: expected exit 2 (BLOCK), got exit $GUARD_EXIT  cmd=[$cmd]"
    if [[ -n "$GUARD_STDERR" ]]; then
      printf '      stderr: %s\n' "$GUARD_STDERR"
    fi
  fi
}

# assert_allow LABEL COMMAND
assert_allow() {
  local label="$1" cmd="$2"
  run_guard "$cmd"
  if [[ "$GUARD_EXIT" -eq 0 ]]; then
    ok "$label (allowed as required, exit 0)"
  else
    fail "$label: expected exit 0 (ALLOW), got exit $GUARD_EXIT  cmd=[$cmd]"
    if [[ -n "$GUARD_STDERR" ]]; then
      printf '      stderr: %s\n' "$GUARD_STDERR"
    fi
  fi
}

# Non-Bash tool calls must always pass through.
assert_non_bash_passthrough() {
  local label="$1" tool="$2" cmd="$3"
  GUARD_EXIT=0
  GUARD_STDERR=""
  local json
  json="$(make_json "$tool" "$cmd")"
  GUARD_STDERR="$(printf '%s' "$json" | bash "$SCRIPT" 2>&1 1>/dev/null)" || GUARD_EXIT=$?
  if [[ "$GUARD_EXIT" -eq 0 ]]; then
    ok "$label (non-Bash tool passed through, exit 0)"
  else
    fail "$label: non-Bash tool [$tool] should exit 0, got exit $GUARD_EXIT"
  fi
}

# ── Adversarial: git global flag bypass cases (BLOCK) ────────────────────────
# These were false-ALLOWs before the fix: value-less git global options
# (--no-pager, --paginate, --bare, --literal-pathspecs) defeated the old
# subcommand detector.  The new per-segment walker skips them correctly.

assert_block "X01 git --no-pager push --force"         "git --no-pager push --force"
assert_block "X02 git --paginate push -f"               "git --paginate push -f"
assert_block "X03 git --bare push --no-verify"          "git --bare push --no-verify"
assert_block "X04 git --literal-pathspecs push --force" "git --literal-pathspecs push --force"
assert_block "X05 git --no-pager merge main"            "git --no-pager merge main"
assert_block "X06 git --no-pager rebase master"         "git --no-pager rebase master"
assert_block "X07 git --no-pager push --force in chain" "git status && git --no-pager push --force"

# Path-to-git: token basename is `git` but the token itself is a full path.
assert_block "X11 /usr/bin/git push --force"  "/usr/bin/git push --force"
# Shell built-in wrapper: `command git` — the `command` token is skipped, git is found next.
assert_block "X12 command git push -f"         "command git push -f"
# Full refname onto-main: basename of refs/heads/main is `main` → must block.
assert_block "X13 git merge refs/heads/main"   "git merge refs/heads/main"

# ── Adversarial: detached-HEAD-at-main (BLOCK) ───────────────────────────────
# Create a temporary git repo, commit to main, detach HEAD at that commit,
# then attempt a git merge.  Must be blocked (bug 3 fix).
_TMP_REPO="$(mktemp -d)"
(
  cd "$_TMP_REPO"
  git init -q
  git config user.email "test@test"
  git config user.name "test"
  git commit -q --allow-empty -m "init"
  # Rename default branch to main.
  git branch -m main 2>/dev/null || true
  # Detach HEAD at the same commit that main points to.
  git checkout -q --detach HEAD
) >/dev/null 2>&1

# Run the guard with CWD set to the temp repo so git rev-parse works.
_detached_exit=0
_detached_json="$(jq -cn --arg cmd "git merge feature-branch" \
  '{"tool_name":"Bash","tool_input":{"command":$cmd}}')"
_detached_stderr="$(
  cd "$_TMP_REPO"
  printf '%s' "$_detached_json" | bash "$SCRIPT" 2>&1 1>/dev/null
)" || _detached_exit=$?

rm -rf "$_TMP_REPO"

if [[ "$_detached_exit" -eq 2 ]]; then
  ok "X08 git merge on detached-HEAD-at-main (blocked as required, exit 2)"
  pass=$((pass + 1))
else
  fail "X08 git merge on detached-HEAD-at-main: expected exit 2 (BLOCK), got exit $_detached_exit"
  failures=$((failures + 1))
fi

# ── Adversarial: false-block regression (ALLOW) ──────────────────────────────
# These were false-BLOCKs before the fix: the -f/-xf flag in a subsequent
# command (tar) and the +done token in echo were matching the whole command
# string.  Scoping checks to push args only fixes this.

assert_allow "X09 git push feat && tar -xf (no false-block on tar -f)"  "git push origin feat && tar -xf a.tar"
assert_allow "X10 git push feat && echo +done (no false-block on +token)" "git push origin feat && echo +done"

# ── BLOCK cases ───────────────────────────────────────────────────────────────

assert_block "B01 git push --force"            "git push --force"
assert_block "B02 git push -f"                 "git push -f"
assert_block "B03 git push --force-with-lease" "git push --force-with-lease"
assert_block "B04 git push +refspec"           "git push origin +HEAD:refs/heads/main"
assert_block "B05 git push --no-verify"        "git push --no-verify"
assert_block "B06 git push --no-gpg-sign"      "git push --no-gpg-sign"
assert_block "B07 git merge main"              "git merge main"
assert_block "B08 git rebase main"             "git rebase main"
assert_block "B09 git merge master"            "git merge master"
assert_block "B10 git rebase master"           "git rebase master"
assert_block "B11 gh pr merge"                 "gh pr merge 42"
assert_block "B12 gh pr close"                 "gh pr close 42"
assert_block "B13 gh pr delete"                "gh pr delete 42"
assert_block "B14 glab mr merge"               "glab mr merge 7"
assert_block "B15 glab mr close"               "glab mr close 7"
assert_block "B16 glab mr delete"              "glab mr delete 7"
assert_block "B17 kubectl apply"               "kubectl apply -f deploy.yaml"
assert_block "B18 kubectl delete"              "kubectl delete pod mypod"
assert_block "B19 kubectl edit"                "kubectl edit deployment app"
assert_block "B20 kubectl patch"               "kubectl patch svc mysvc -p '{\"spec\":{}}'"
assert_block "B21 kubectl scale"               "kubectl scale deploy/app --replicas=3"
assert_block "B22 kubectl replace"             "kubectl replace -f svc.yaml"
assert_block "B23 kubectl rollout"             "kubectl rollout restart deploy/app"
assert_block "B24 helm install"                "helm install myapp ./chart"
assert_block "B25 helm upgrade"                "helm upgrade myapp ./chart"
assert_block "B26 helm uninstall"              "helm uninstall myapp"
assert_block "B27 helm rollback"               "helm rollback myapp 1"

# Chained commands — redline inside a pipeline/sequence must still be caught.
assert_block "B28 git push --force in chain"  "git status && git push --force"
assert_block "B29 kubectl delete in pipe"     "echo 'cleaning' | kubectl delete -f all.yaml"

# Variants with git -C <path>
assert_block "B30 git -C path push --force"   "git -C /some/repo push --force"
assert_block "B31 env-var prefix push -f"     "GIT_SSH_COMMAND=ssh git push -f"

# ── ALLOW cases ───────────────────────────────────────────────────────────────

assert_allow "A01 git push origin feat-x"      "git push origin feat-x"
assert_allow "A02 git push origin main (plain)" "git push origin main"
assert_allow "A03 git push (bare)"             "git push"
assert_allow "A04 git push -u origin main"     "git push -u origin main"
assert_allow "A05 git commit"                  "git commit -m 'msg'"
assert_allow "A06 ls"                          "ls -la"
assert_allow "A07 kubectl get pods"            "kubectl get pods"
assert_allow "A08 kubectl describe"            "kubectl describe pod mypod"
assert_allow "A09 kubectl logs"                "kubectl logs mypod -f"
assert_allow "A10 kubectl events"              "kubectl events"
assert_allow "A11 helm list"                   "helm list"
assert_allow "A12 helm status"                 "helm status myapp"
assert_allow "A13 helm get values"             "helm get values myapp"
assert_allow "A14 git diff"                    "git diff origin/main...HEAD"
assert_allow "A15 echo with --force string"    "echo 'git push --force is bad'"
assert_allow "A16 gh pr create"                "gh pr create --title 'feat: x'"
assert_allow "A17 git push --tags"             "git push --tags"
assert_allow "A18 glab mr create"              "glab mr create --title 'feat'"
assert_allow "A19 git log"                     "git log --oneline -10"
assert_allow "A20 helm get all"                "helm get all myapp"

# Non-Bash tools must always pass through regardless of content.
assert_non_bash_passthrough "NB01 Edit tool"  "Edit"  "git push --force"
assert_non_bash_passthrough "NB02 Write tool" "Write" "kubectl delete all"

# Malformed / empty input must not crash (exit 0 = fail-open).
GUARD_EXIT=0
printf '' | bash "$SCRIPT" 2>/dev/null || GUARD_EXIT=$?
if [[ "$GUARD_EXIT" -eq 0 ]]; then
  ok "M01 empty stdin exits 0 (fail-safe open)"
else
  fail "M01 empty stdin: expected exit 0, got $GUARD_EXIT"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
printf '\n'
if [[ "$failures" -gt 0 ]]; then
  printf 'SELFTEST FAILED: %d case(s) failed  (%d passed)\n' "$failures" "$pass"
  exit 1
else
  printf 'SELFTEST OK: all %d cases passed\n' "$pass"
  exit 0
fi
