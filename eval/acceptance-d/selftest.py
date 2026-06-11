#!/usr/bin/env python3
"""selftest.py — symmetric exchange selftest + acceptance runner for issue #30.

Two modes:

  selftest mode (no args or --selftest):
      Runs the common-code validator (check_common_code.py) against the local
      good+bad fixture set and asserts expected exit codes and FAIL codes.
      Prints one line per fixture: PASS or FAIL with reason.
      Exits 0 if all assertions hold; nonzero otherwise.

  acceptance mode (--acceptance <path-to-D-repo>):
      Parameterized by a path to D's cloned repository.
      For each of checks 1-4 declared in issue #30:
        - If D's artifact exists at the expected path, runs the check.
        - If D's artifact is missing, prints SKIP with reason.
      Exits 0 only if all runnable checks pass; nonzero on any failure or
      unexpected error.

Validator path:
      The selftest mode requires check_common_code.py. Default expected
      location: <repo_root>/scripts/check_common_code.py (i.e. the issue-#29
      branch delivers it there). Override with --validator <path>.

      For testing against the workspace copy before issue-#29 merges, pass:
        python3 selftest.py --validator /workspace/check_common_code.py

stdlib only. No network. Fails closed.
"""
import argparse
import json
import os
import subprocess
import sys


# ---------------------------------------------------------------------------
# Paths relative to THIS file's directory (eval/acceptance-d/)
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FIXTURES = os.path.join(HERE, "fixtures")

DEFAULT_VALIDATOR = os.path.join(REPO_ROOT, "scripts", "check_common_code.py")

# ---------------------------------------------------------------------------
# Symmetric-exchange fixture expectations
# Each tuple: (fixture_filename, expected_exit_code, expected_fail_code_or_None)
# expected_fail_code is the first token after "FAIL " in the output; None means
# we expect exit 0 (success output begins with "OK").
# ---------------------------------------------------------------------------
FIXTURES_SPEC = [
    ("good.jsonl",  0, None),
    ("bad1.jsonl",  1, "RETRIEVAL"),
    ("bad2.jsonl",  1, "JSON"),
    ("bad3.jsonl",  1, "SHAPE"),
    ("big.jsonl",   1, "BUDGET"),
]


def run(cmd):
    """Run command list; return (exit_code, stdout_text)."""
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.returncode, result.stdout.strip()


def extract_fail_code(output):
    """Return the code token from 'FAIL <CODE> ...' or 'FAIL <CODE>:' output, or None."""
    for line in output.splitlines():
        if line.startswith("FAIL "):
            parts = line.split()
            if len(parts) >= 2:
                # Strip trailing colon: 'FAIL BUDGET: ...' -> 'BUDGET'
                return parts[1].rstrip(":")
    return None


def selftest(validator_path):
    """Run all fixture assertions. Returns True if all pass."""
    if not os.path.isfile(validator_path):
        print(f"ERROR: validator not found at {validator_path}")
        print(f"  (issue #29 branch delivers it to scripts/check_common_code.py)")
        print(f"  pass --validator <path> to override")
        return False

    all_ok = True
    print(f"Validator: {validator_path}")
    print(f"Fixtures:  {FIXTURES}")
    print()

    for fixture, expected_exit, expected_code in FIXTURES_SPEC:
        fpath = os.path.join(FIXTURES, fixture)
        if not os.path.isfile(fpath):
            print(f"  MISSING  {fixture} — fixture file not found at {fpath}")
            all_ok = False
            continue

        exit_code, output = run([sys.executable, validator_path, fpath])

        if exit_code != expected_exit:
            print(f"  FAIL     {fixture}: expected exit {expected_exit}, got {exit_code}")
            print(f"           output: {output[:200]}")
            all_ok = False
            continue

        if expected_code is not None:
            got_code = extract_fail_code(output)
            if got_code != expected_code:
                print(f"  FAIL     {fixture}: expected FAIL code {expected_code!r}, got {got_code!r}")
                print(f"           output: {output[:200]}")
                all_ok = False
                continue
            print(f"  PASS     {fixture}: exit={exit_code}, FAIL {expected_code} (as expected)")
        else:
            if not output.startswith("OK"):
                print(f"  FAIL     {fixture}: expected 'OK ...' output, got: {output[:200]}")
                all_ok = False
                continue
            print(f"  PASS     {fixture}: exit=0, {output.splitlines()[0]}")

    print()
    if all_ok:
        print("selftest: ALL PASS")
    else:
        print("selftest: FAILURES DETECTED")
    return all_ok


# ---------------------------------------------------------------------------
# Acceptance mode: checks 1-4 from issue #30
# ---------------------------------------------------------------------------

def check_issue_answer(d_repo):
    """Check 1: issue_answer_check.py — comment-3 must fail, comment-9 must pass."""
    script = os.path.join(d_repo, "issue_answer_check.py")
    if not os.path.isfile(script):
        print("  SKIP  check-1 (issue_answer_check.py): file not found in D's repo")
        return None  # skipped

    c3 = os.path.join(FIXTURES, "comment-3.txt")
    c9 = os.path.join(FIXTURES, "comment-9.txt")
    ok = True

    exit3, out3 = run([sys.executable, script, c3])
    if exit3 == 0:
        print(f"  FAIL  check-1: comment-3 (expected FAIL) returned exit 0")
        print(f"        output: {out3[:200]}")
        ok = False
    else:
        print(f"  PASS  check-1a: comment-3 rejected (exit={exit3})")

    exit9, out9 = run([sys.executable, script, c9])
    if exit9 != 0:
        print(f"  FAIL  check-1: comment-9 (expected PASS) returned exit {exit9}")
        print(f"        output: {out9[:200]}")
        ok = False
    else:
        print(f"  PASS  check-1b: comment-9 accepted (exit=0)")

    return ok


def check_drift_guard(d_repo):
    """Check 2: drift_guard.py — ledger machine-readable, >=10 entries, >=1 'мой-дрейф';
    commit without go:user tag must exit nonzero."""
    script = os.path.join(d_repo, "drift_guard.py")
    if not os.path.isfile(script):
        print("  SKIP  check-2 (drift_guard.py): file not found in D's repo")
        return None

    ok = True

    # 2a: run with a fake commit message that has no go:user tag
    exit_code, out = run([sys.executable, script, "--check-commit", "fix: some change"])
    if exit_code == 0:
        print("  FAIL  check-2a: commit without go:user tag returned exit 0 (should be nonzero)")
        ok = False
    else:
        print(f"  PASS  check-2a: commit without go:user tag rejected (exit={exit_code})")

    # 2b: check ledger exists and has required properties
    # Try common ledger paths
    ledger_candidates = [
        os.path.join(d_repo, "drift_ledger.jsonl"),
        os.path.join(d_repo, "drift-ledger.jsonl"),
        os.path.join(d_repo, "ledger.jsonl"),
    ]
    ledger_path = None
    for c in ledger_candidates:
        if os.path.isfile(c):
            ledger_path = c
            break

    if ledger_path is None:
        # Try asking drift_guard.py for ledger path
        exit_l, out_l = run([sys.executable, script, "--ledger-path"])
        if exit_l == 0 and out_l.strip():
            candidate = out_l.strip()
            if not os.path.isabs(candidate):
                candidate = os.path.join(d_repo, candidate)
            if os.path.isfile(candidate):
                ledger_path = candidate

    if ledger_path is None:
        print("  FAIL  check-2b: ledger file not found (tried drift_ledger.jsonl, drift-ledger.jsonl, ledger.jsonl)")
        ok = False
    else:
        entries = []
        with open(ledger_path, encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                try:
                    entries.append(json.loads(s))
                except Exception:
                    pass

        # >=10 entries with source tag
        entries_with_source = [e for e in entries if isinstance(e, dict) and e.get("source")]
        if len(entries_with_source) < 10:
            print(f"  FAIL  check-2b: ledger has {len(entries_with_source)} entries with source tag (need >=10)")
            ok = False
        else:
            print(f"  PASS  check-2b: ledger has {len(entries_with_source)} entries with source tag")

        # >=1 entry tagged мой-дрейф
        drift_entries = [e for e in entries if isinstance(e, dict)
                         and str(e.get("source", "")).lower() in ("мой-дрейф", "мой_дрейф", "my-drift")]
        if len(drift_entries) < 1:
            print("  FAIL  check-2c: no entry tagged 'мой-дрейф' in ledger")
            ok = False
        else:
            print(f"  PASS  check-2c: found {len(drift_entries)} 'мой-дрейф' entry(ies) in ledger")

    return ok


def check_frontier(d_repo):
    """Check 3: frontier.py — 1 quality point + 0 cost points -> INSUFFICIENT_POINTS, no curve."""
    script = os.path.join(d_repo, "frontier.py")
    if not os.path.isfile(script):
        print("  SKIP  check-3 (frontier.py): file not found in D's repo")
        return None

    # Run with minimal args: 1 quality point, 0 cost points
    exit_code, out = run([sys.executable, script, "--quality-points", "1", "--cost-points", "0"])
    if "INSUFFICIENT_POINTS" not in out:
        print(f"  FAIL  check-3: expected INSUFFICIENT_POINTS in output, got: {out[:300]}")
        return False
    if exit_code == 0:
        # Some implementations exit 0 with INSUFFICIENT_POINTS text — check no curve was drawn
        # by verifying no plot file was created
        curve_files = [f for f in os.listdir(d_repo) if f.endswith((".png", ".svg", ".pdf"))]
        if curve_files:
            print(f"  FAIL  check-3: INSUFFICIENT_POINTS present but curve file(s) generated: {curve_files}")
            return False
    print(f"  PASS  check-3: INSUFFICIENT_POINTS returned (exit={exit_code})")
    return True


def check_abc_classification(d_repo):
    """Check 4: [A]/[B]/[C] classification — artifact exists; >=1 deterministic class-A test."""
    # Look for the classification artifact
    candidates = [
        os.path.join(d_repo, "enforcement_classes.py"),
        os.path.join(d_repo, "abc_classification.py"),
        os.path.join(d_repo, "enforce_classes.py"),
        os.path.join(d_repo, "classification.py"),
    ]
    artifact = None
    for c in candidates:
        if os.path.isfile(c):
            artifact = c
            break

    if artifact is None:
        # Also check docs/
        docs_candidates = [
            os.path.join(d_repo, "docs", "enforcement-classes.md"),
            os.path.join(d_repo, "docs", "abc-classes.md"),
            os.path.join(d_repo, "ABC_CLASSIFICATION.md"),
        ]
        for c in docs_candidates:
            if os.path.isfile(c):
                artifact = c
                break

    if artifact is None:
        print("  SKIP  check-4 ([A]/[B]/[C] classification): artifact not found in D's repo")
        print("        (expected: enforcement_classes.py, abc_classification.py, or docs/enforcement-classes.md)")
        return None

    print(f"  FOUND check-4: classification artifact at {artifact}")

    # Run any test file that exercises class-A deterministically
    test_candidates = [
        os.path.join(d_repo, "test_abc.py"),
        os.path.join(d_repo, "test_enforcement_classes.py"),
        os.path.join(d_repo, "tests", "test_abc.py"),
        os.path.join(d_repo, "tests", "test_classification.py"),
    ]
    test_file = None
    for c in test_candidates:
        if os.path.isfile(c):
            test_file = c
            break

    if test_file is None:
        print("  SKIP  check-4b: no class-A test file found (artifact present, test absent)")
        return None

    exit_code, out = run([sys.executable, test_file])
    if exit_code != 0:
        print(f"  FAIL  check-4b: class-A test returned exit {exit_code}")
        print(f"        output: {out[:300]}")
        return False

    print(f"  PASS  check-4b: class-A test passed (exit=0)")
    return True


def acceptance(d_repo, validator_path):
    """Run all acceptance checks for D's repo."""
    if not os.path.isdir(d_repo):
        print(f"ERROR: D's repo not found at {d_repo}")
        return False

    print(f"Acceptance checks against D's repo: {d_repo}")
    print(f"Validator: {validator_path}")
    print()

    results = []

    # Run selftest first (our symmetric exchange checks)
    print("=== Symmetric exchange selftest ===")
    st_ok = selftest(validator_path)
    results.append(("selftest", st_ok))
    print()

    # Check 1
    print("=== Check 1: issue_answer_check.py (tone gate) ===")
    r1 = check_issue_answer(d_repo)
    results.append(("check-1", r1))
    print()

    # Check 2
    print("=== Check 2: drift_guard.py (drift ledger) ===")
    r2 = check_drift_guard(d_repo)
    results.append(("check-2", r2))
    print()

    # Check 3
    print("=== Check 3: frontier.py (INSUFFICIENT_POINTS) ===")
    r3 = check_frontier(d_repo)
    results.append(("check-3", r3))
    print()

    # Check 4
    print("=== Check 4: [A]/[B]/[C] classification ===")
    r4 = check_abc_classification(d_repo)
    results.append(("check-4", r4))
    print()

    # Summary
    print("=== Summary ===")
    all_runnable_passed = True
    for name, result in results:
        if result is None:
            print(f"  SKIP  {name}")
        elif result:
            print(f"  PASS  {name}")
        else:
            print(f"  FAIL  {name}")
            all_runnable_passed = False

    print()
    if all_runnable_passed:
        print("acceptance: ALL RUNNABLE CHECKS PASSED")
    else:
        print("acceptance: FAILURES DETECTED — D's artifacts do not meet acceptance criteria")
    return all_runnable_passed


def main():
    parser = argparse.ArgumentParser(
        description="Acceptance kit selftest and acceptance runner for issue #30"
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        default=False,
        help="Run selftest mode (default when no --acceptance given)",
    )
    parser.add_argument(
        "--acceptance",
        metavar="D_REPO_PATH",
        help="Run acceptance mode against D's cloned repository at this path",
    )
    parser.add_argument(
        "--validator",
        metavar="PATH",
        default=DEFAULT_VALIDATOR,
        help=f"Path to check_common_code.py (default: {DEFAULT_VALIDATOR})",
    )
    args = parser.parse_args()

    if args.acceptance:
        ok = acceptance(args.acceptance, args.validator)
    else:
        ok = selftest(args.validator)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
