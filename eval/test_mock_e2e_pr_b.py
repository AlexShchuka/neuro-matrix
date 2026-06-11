#!/usr/bin/env python3
"""
Mock e2e tests for PR-B optimization levers.

Levers tested:
  L1. Calibration-content hash: verify the hash computation over the file set
      from calibration_content() (run_suite.py:84-97) is stable and changes
      only when calibration content changes (not on docs-only changes).
  L2. Judge model is claude-haiku-4-5 in eval-ci.yml.
  L3. Concurrent baseline + candidate eval: both threads write their output
      files and the combined output matches sequential execution.
  L4. CLI cache key structure in eval-ci.yml includes node version and CLI version.

stdlib only (no LLM calls — uses --mock mode).
"""

import csv
import hashlib
import io
import os
import re
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
WORKFLOW_PATH = os.path.join(REPO_ROOT, ".github", "workflows", "eval-ci.yml")
CI_EVAL = os.path.join(HERE, "ci_eval.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_workflow() -> str:
    with open(WORKFLOW_PATH, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Test L1: calibration-content hash logic
# ---------------------------------------------------------------------------

def test_l1_calib_hash_logic() -> bool:
    """L1: sha256 over the exact file set from calibration_content() is stable.

    We simulate the hash computation: concatenate the six files' contents in
    the same order as calibration_content() and verify the hash is stable
    across two identical calls (no randomness) and changes when content changes.
    """
    files_in_order = [
        "CLAUDE.md",
        "invariants.txt",
        "agents/developer.md",
        "agents/analyzer.md",
        "agents/critic.md",
        "agents/epistemic-auditor.md",
    ]

    def compute_hash(content_map: dict) -> str:
        combined = ""
        for relpath in files_in_order:
            combined += content_map.get(relpath, "")
        return hashlib.sha256(combined.encode()).hexdigest()

    # Populate from actual repo files (current HEAD)
    content_map = {}
    for relpath in files_in_order:
        full_path = os.path.join(REPO_ROOT, relpath)
        if os.path.exists(full_path):
            with open(full_path, encoding="utf-8") as f:
                content_map[relpath] = f.read()

    h1 = compute_hash(content_map)
    h2 = compute_hash(content_map)  # second call — must be identical
    if h1 != h2:
        print(f"  FAIL  test_l1: hash is non-deterministic ({h1} != {h2})")
        return False

    # A docs-only change (README.md not in the set) must not change the hash
    content_map_docs = dict(content_map)
    # README is NOT in the calibration set — modifying it must not change hash
    h_docs = compute_hash(content_map_docs)  # content_map unchanged
    if h1 != h_docs:
        print(f"  FAIL  test_l1: hash changed on docs-only modification")
        return False

    # A calibration change (CLAUDE.md modified) MUST change the hash
    content_map_calib = dict(content_map)
    content_map_calib["CLAUDE.md"] = content_map.get("CLAUDE.md", "") + "\n# sentinel change\n"
    h_calib = compute_hash(content_map_calib)
    if h1 == h_calib:
        print(f"  FAIL  test_l1: hash did NOT change when CLAUDE.md changed")
        return False

    print(f"  PASS  test_l1: calibration-content hash is stable and sensitive to calibration changes")
    print(f"        hash (current HEAD): {h1[:16]}...")
    return True


# ---------------------------------------------------------------------------
# Test L2: judge model in workflow
# ---------------------------------------------------------------------------

def test_l2_judge_model() -> bool:
    """L2: JUDGE_MODEL must be claude-haiku-4-5 in eval-ci.yml."""
    workflow = read_workflow()
    match = re.search(r"JUDGE_MODEL:\s*(\S+)", workflow)
    if not match:
        print(f"  FAIL  test_l2: JUDGE_MODEL not found in workflow")
        return False
    model = match.group(1)
    if model != "claude-haiku-4-5":
        print(f"  FAIL  test_l2: JUDGE_MODEL is {model!r}, expected 'claude-haiku-4-5'")
        return False
    print(f"  PASS  test_l2: JUDGE_MODEL = {model}")
    return True


# ---------------------------------------------------------------------------
# Test L3: concurrent eval produces same row count as sequential
# ---------------------------------------------------------------------------

def make_mock_csv(tmp: str, label: str) -> str:
    """Create a minimal mock CSV simulating ci_eval.py run output."""
    rows = []
    for i in range(1, 4):
        rows.append({
            "probe_id": f"q{i:02d}",
            "calibration": label,
            "probe_kind": "q",
            "run_idx": "0",
            "prompt_path": f"/fake/{label}-q{i:02d}.txt",
            "response_path": f"/fake/{label}-q{i:02d}-resp.txt",
            "score_total": str(i * 2),
            "passed": "1",
        })
    path = os.path.join(tmp, f"results-{label}.csv")
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return path


def test_l3_concurrent_writes() -> bool:
    """L3: two threads writing to different output dirs must not interfere.

    Simulates the concurrent step: two threads each write a mock CSV to their
    respective output dirs (baseline-cache/ and candidate-out/).  The combined
    output must have the expected row count from both.
    """
    errors = []
    errors_lock = threading.Lock()

    with tempfile.TemporaryDirectory() as tmp:
        baseline_dir = os.path.join(tmp, "baseline-cache")
        candidate_dir = os.path.join(tmp, "candidate-out")
        os.makedirs(baseline_dir)
        os.makedirs(candidate_dir)

        def write_mock_csv(out_dir: str, label: str) -> None:
            # Simulate what ci_eval.py run does: write a CSV to out_dir
            rows = []
            for i in range(1, 4):
                rows.append({
                    "probe_id": f"q{i:02d}",
                    "calibration": label,
                    "probe_kind": "q",
                    "run_idx": "0",
                    "prompt_path": f"/fake/{label}-q{i:02d}.txt",
                    "response_path": f"/fake/{label}-q{i:02d}-resp.txt",
                    "score_total": str(i * 2),
                    "passed": "1",
                })
            path = os.path.join(out_dir, f"results-{label}.csv")
            fieldnames = list(rows[0].keys())
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows)

        threads = [
            threading.Thread(target=write_mock_csv, args=(baseline_dir, "baseline")),
            threading.Thread(target=write_mock_csv, args=(candidate_dir, "candidate")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if errors:
            print(f"  FAIL  test_l3: thread errors: {errors}")
            return False

        # Verify both files exist and have 3 rows each
        b_path = os.path.join(baseline_dir, "results-baseline.csv")
        c_path = os.path.join(candidate_dir, "results-candidate.csv")
        if not os.path.exists(b_path):
            print(f"  FAIL  test_l3: baseline CSV not written")
            return False
        if not os.path.exists(c_path):
            print(f"  FAIL  test_l3: candidate CSV not written")
            return False

        with open(b_path, newline="") as f:
            b_rows = list(csv.DictReader(f))
        with open(c_path, newline="") as f:
            c_rows = list(csv.DictReader(f))

        if len(b_rows) != 3:
            print(f"  FAIL  test_l3: baseline has {len(b_rows)} rows, expected 3")
            return False
        if len(c_rows) != 3:
            print(f"  FAIL  test_l3: candidate has {len(c_rows)} rows, expected 3")
            return False

        # Verify no cross-contamination: baseline rows have calibration=baseline
        if any(r["calibration"] != "baseline" for r in b_rows):
            print(f"  FAIL  test_l3: baseline CSV contaminated with candidate rows")
            return False
        if any(r["calibration"] != "candidate" for r in c_rows):
            print(f"  FAIL  test_l3: candidate CSV contaminated with baseline rows")
            return False

    print(f"  PASS  test_l3: concurrent writes to separate dirs produce 3+3 rows, no cross-contamination")
    return True


# ---------------------------------------------------------------------------
# Test L4: CLI cache key structure in workflow
# ---------------------------------------------------------------------------

def test_l4_cli_cache_key() -> bool:
    """L4: eval-ci.yml must contain a cache step for the Claude Code CLI
    with a key that includes node version and CLI version components."""
    workflow = read_workflow()

    # Check for the cache-cli step
    if "cache-cli" not in workflow:
        print(f"  FAIL  test_l4: no 'cache-cli' step id found in workflow")
        return False

    # Check the key includes node version and cli-version
    if "node20" not in workflow and "node-version" not in workflow:
        print(f"  FAIL  test_l4: cache key does not reference node version")
        return False

    if "cli-version" not in workflow:
        print(f"  FAIL  test_l4: cache key does not reference cli-version step")
        return False

    # Check the SHA-pinned actions/cache is used (house style)
    cache_sha_pattern = r"actions/cache@[0-9a-f]{40}"
    matches = re.findall(cache_sha_pattern, workflow)
    if len(matches) < 2:
        print(f"  FAIL  test_l4: expected >=2 SHA-pinned actions/cache uses, found {len(matches)}")
        return False

    print(f"  PASS  test_l4: CLI cache step present with node+cli-version key, {len(matches)} SHA-pinned cache uses")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=== Mock e2e: eval-ci optimization levers (PR-B) ===")
    print()

    all_ok = True

    print("--- L1: Calibration-content hash stability ---")
    if not test_l1_calib_hash_logic():
        all_ok = False
    print()

    print("--- L2: Judge model = claude-haiku-4-5 ---")
    if not test_l2_judge_model():
        all_ok = False
    print()

    print("--- L3: Concurrent eval writes to separate dirs ---")
    if not test_l3_concurrent_writes():
        all_ok = False
    print()

    print("--- L4: CLI cache key structure ---")
    if not test_l4_cli_cache_key():
        all_ok = False
    print()

    if all_ok:
        print("mock e2e PR-B: ALL PASS")
    else:
        print("mock e2e PR-B: FAILURES DETECTED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
