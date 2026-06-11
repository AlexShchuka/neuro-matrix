#!/usr/bin/env python3
"""selftest_check_common_code.py — stdlib-only selftest for check_common_code.py.

Runs the validator against each fixture file and asserts the expected exit code
and FAIL code. Fails with a non-zero exit code and prints a summary of failures.

Usage: python3 scripts/selftest_check_common_code.py
Run from the repository root or any directory; paths are resolved relative to this
script's own location.

stdlib only, deterministic, fails closed.
"""
import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VALIDATOR = os.path.join(HERE, "check_common_code.py")
FIXTURES = os.path.join(HERE, "fixtures")
REPO_ROOT = os.path.dirname(HERE)

# (fixture_file_or_path, expected_exit_code, expected_fail_code_or_None)
# Entries are either bare filenames (resolved under FIXTURES) or absolute paths.
CASES = [
    ("good.jsonl",  0, None),
    ("bad1.jsonl",  1, "FAIL RETRIEVAL"),
    ("bad2.jsonl",  1, "FAIL JSON"),
    ("bad3.jsonl",  1, "FAIL SHAPE"),
    ("big.jsonl",   1, "FAIL BUDGET"),
    ("bad5.jsonl",  1, "FAIL SIGNATURE"),
    ("bad6.jsonl",  1, "FAIL SHAPE"),
    # repo-root sample must always be valid (guards against sample rot)
    (os.path.join(REPO_ROOT, "common-code.sample.jsonl"), 0, None),
]

failures = []
for filename, want_code, want_fail in CASES:
    path = filename if os.path.isabs(filename) else os.path.join(FIXTURES, filename)
    result = subprocess.run(
        [sys.executable, VALIDATOR, path],
        capture_output=True, text=True
    )
    output = (result.stdout + result.stderr).strip()
    ok = True
    notes = []
    if result.returncode != want_code:
        ok = False
        notes.append(
            f"exit code: got {result.returncode}, want {want_code}"
        )
    if want_fail is not None and want_fail not in output:
        ok = False
        notes.append(
            f"expected '{want_fail}' in output, got: {output!r}"
        )
    status = "PASS" if ok else "FAIL"
    print(f"{status}  {filename:20s}  exit={result.returncode}  {output[:80]}")
    if not ok:
        for note in notes:
            print(f"      !! {note}")
        failures.append(filename)

print()
if failures:
    print(f"SELFTEST FAILED: {len(failures)} case(s): {failures}")
    sys.exit(1)
else:
    print(f"SELFTEST OK: all {len(CASES)} cases passed")
    sys.exit(0)
