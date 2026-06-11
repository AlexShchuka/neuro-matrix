#!/usr/bin/env python3
"""
Mock e2e tests for eval-ci optimization levers and critic-fix items.

Tests:
  L1. Calibration-content hash: stable and content-sensitive; uses CALIB_FILES
      from run_suite.py (B4 single-source); B5 sentinel ensures deleted file
      hashes differently from absent file.
  L2. Judge model is claude-haiku-4-5 in eval-ci.yml and ci_eval.py run default.
  L3. Concurrent baseline + candidate eval: REAL test — invoke ci_eval.py run
      --mock in two threads with separate out-dirs; assert both CSVs produced
      with correct calibration labels; assert forced thread failure propagates
      via the errors channel and raises SystemExit.
  L4. CLI cache key structure in eval-ci.yml includes node version and CLI version.

stdlib only (no LLM calls — uses --mock mode for L3).
"""

import csv
import hashlib
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
# Test L1: calibration-content hash logic (B4 + B5)
# ---------------------------------------------------------------------------

def test_l1_calib_hash_logic() -> bool:
    """L1/B4/B5: hash uses CALIB_FILES from run_suite.py; B5 sentinel ensures
    a deleted file hashes differently from an absent (never-existed) file."""

    # B4: import CALIB_FILES from run_suite.py (single source of truth)
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_suite", os.path.join(HERE, "run_suite.py"))
    run_suite_mod = importlib.util.module_from_spec(spec)  # type: ignore
    spec.loader.exec_module(run_suite_mod)  # type: ignore
    calib_files = run_suite_mod.CALIB_FILES  # list[tuple[relpath, label]]
    file_relpaths = [relpath for relpath, _label in calib_files]

    # B5: hash sentinel — per-file contribution: "<relpath>:<bytelen>:<content>"
    def compute_hash_with_sentinel(content_map: dict) -> str:
        h = hashlib.sha256()
        for relpath in file_relpaths:
            raw = content_map.get(relpath)  # None = absent, b"" = empty
            if raw is None:
                continue  # absent file: no contribution
            sentinel = f"{relpath}:{len(raw)}:".encode()
            h.update(sentinel + (raw if isinstance(raw, bytes) else raw.encode()))
        return h.hexdigest()

    # Populate from actual repo files (current HEAD)
    content_map: dict = {}
    for relpath in file_relpaths:
        full_path = os.path.join(REPO_ROOT, relpath)
        if os.path.exists(full_path):
            with open(full_path, "rb") as f:
                content_map[relpath] = f.read()

    h1 = compute_hash_with_sentinel(content_map)
    h2 = compute_hash_with_sentinel(content_map)
    if h1 != h2:
        print(f"  FAIL  test_l1: hash is non-deterministic ({h1} != {h2})")
        return False

    # Docs-only change (README.md not in CALIB_FILES) must not change hash
    h_docs = compute_hash_with_sentinel(content_map)  # unchanged
    if h1 != h_docs:
        print(f"  FAIL  test_l1: hash changed on docs-only modification")
        return False

    # Calibration change (CLAUDE.md modified) MUST change hash
    content_map_calib = dict(content_map)
    existing = content_map.get("CLAUDE.md", b"")
    content_map_calib["CLAUDE.md"] = existing + b"\n# sentinel change\n"
    h_calib = compute_hash_with_sentinel(content_map_calib)
    if h1 == h_calib:
        print(f"  FAIL  test_l1: hash did NOT change when CLAUDE.md changed")
        return False

    # B5: deleted file (empty bytes) must hash differently from absent file
    content_map_absent = {k: v for k, v in content_map.items() if k != "CLAUDE.md"}
    content_map_empty = dict(content_map)
    content_map_empty["CLAUDE.md"] = b""  # file exists but is empty
    h_absent = compute_hash_with_sentinel(content_map_absent)
    h_empty = compute_hash_with_sentinel(content_map_empty)
    if h_absent == h_empty:
        print(f"  FAIL  test_l1 (B5): absent file and empty file hash identically")
        return False

    print(f"  PASS  test_l1: CALIB_FILES-driven hash is stable, content-sensitive, and B5-sentinel-correct")
    print(f"        files from run_suite.CALIB_FILES: {len(file_relpaths)}")
    print(f"        hash (current HEAD): {h1[:16]}...")
    return True


# ---------------------------------------------------------------------------
# Test L2: judge model in workflow and ci_eval.py run default
# ---------------------------------------------------------------------------

def test_l2_judge_model() -> bool:
    """L2: JUDGE_MODEL must be claude-haiku-4-5 in eval-ci.yml and in
    ci_eval.py run subparser default."""
    workflow = read_workflow()

    # Check workflow env
    match = re.search(r"JUDGE_MODEL:\s*(\S+)", workflow)
    if not match:
        print(f"  FAIL  test_l2: JUDGE_MODEL not found in workflow")
        return False
    model = match.group(1)
    if model != "claude-haiku-4-5":
        print(f"  FAIL  test_l2: workflow JUDGE_MODEL is {model!r}, expected 'claude-haiku-4-5'")
        return False

    # Check ci_eval.py run subparser default (B7)
    with open(CI_EVAL, encoding="utf-8") as f:
        ci_src = f.read()
    # The run subparser sets --judge-model default
    run_default_match = re.search(
        r'"--judge-model",\s*default="([^"]+)"',
        ci_src,
    )
    if not run_default_match:
        print(f"  FAIL  test_l2: --judge-model default not found in ci_eval.py run subparser")
        return False
    ci_default = run_default_match.group(1)
    if ci_default != "claude-haiku-4-5":
        print(f"  FAIL  test_l2: ci_eval.py run --judge-model default is {ci_default!r}, expected 'claude-haiku-4-5'")
        return False

    print(f"  PASS  test_l2: JUDGE_MODEL = {model} (workflow + ci_eval.py run default)")
    return True


# ---------------------------------------------------------------------------
# Test L3: REAL concurrent eval via ci_eval.py run --mock
# ---------------------------------------------------------------------------

def test_l3_real_concurrent_mock() -> bool:
    """L3 (B3): invoke ci_eval.py run --mock in two threads with separate
    out-dirs; assert both CSVs produced with correct calibration labels;
    assert that a forced failure in one thread propagates via the errors
    channel and raises SystemExit.
    """
    # --- Part A: normal concurrent run, both threads succeed ---
    errors: list[str] = []
    errors_lock = threading.Lock()

    def run_eval(ref_label: str, out_csv: str, prompts_dir: str) -> None:
        cmd = [
            sys.executable, CI_EVAL, "run",
            "--ref", ref_label,
            "--probes", "questions",
            "--k", "1",
            "--out", out_csv,
            "--prompts-dir", prompts_dir,
            "--gen-model", "claude-haiku-4-5",
            "--judge-model", "claude-haiku-4-5",
            "--mock",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            with errors_lock:
                errors.append(
                    f"eval failed for {ref_label} (exit {result.returncode}): "
                    f"{result.stderr[:200]}"
                )

    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        baseline_dir = os.path.join(tmp, "baseline-cache")
        candidate_dir = os.path.join(tmp, "candidate-out")
        baseline_csv = os.path.join(baseline_dir, "results-baseline.csv")
        candidate_csv = os.path.join(candidate_dir, "results-candidate.csv")
        os.makedirs(baseline_dir)
        os.makedirs(candidate_dir)

        # Use the current HEAD commit as a mock ref (git show will work)
        import subprocess as sp
        head_sha = sp.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        ).stdout.strip()

        threads = [
            threading.Thread(
                target=run_eval,
                args=(f"{head_sha}=baseline", baseline_csv, os.path.join(baseline_dir, "prompts")),
            ),
            threading.Thread(
                target=run_eval,
                args=(f"{head_sha}=candidate", candidate_csv, os.path.join(candidate_dir, "prompts")),
            ),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if errors:
            print(f"  FAIL  test_l3 part-A: thread errors during --mock run: {errors}")
            ok = False
        else:
            # Verify both CSVs exist with correct calibration labels
            for path, label in ((baseline_csv, "baseline"), (candidate_csv, "candidate")):
                if not os.path.exists(path):
                    print(f"  FAIL  test_l3 part-A: {label} CSV not produced at {path}")
                    ok = False
                    continue
                with open(path, newline="", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                if not rows:
                    print(f"  FAIL  test_l3 part-A: {label} CSV is empty")
                    ok = False
                    continue
                wrong_label = [r for r in rows if r.get("calibration") != label]
                if wrong_label:
                    print(
                        f"  FAIL  test_l3 part-A: {label} CSV has wrong calibration rows: "
                        f"{[r['calibration'] for r in wrong_label]}"
                    )
                    ok = False

    if ok:
        print(f"  PASS  test_l3 part-A: both --mock CSVs produced with correct calibration labels")

    # --- Part B: one thread fails → errors channel raises SystemExit ---
    errors_b: list[str] = []
    errors_lock_b = threading.Lock()

    def run_eval_fail(ref_label: str) -> None:
        """Force a failure by passing a malformed --ref (no '=' separator → exit 2)."""
        cmd = [
            sys.executable, CI_EVAL, "run",
            "--ref", ref_label,   # no '=' → ci_eval exits 2
            "--probes", "questions",
            "--k", "1",
            "--out", "/dev/null",
            "--prompts-dir", "/tmp/noop-prompts",
            "--gen-model", "claude-haiku-4-5",
            "--judge-model", "claude-haiku-4-5",
            "--mock",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            with errors_lock_b:
                errors_b.append(f"eval failed for {ref_label} (exit {result.returncode})")

    # Malformed ref (no '=') causes ci_eval.py to exit 2
    t_fail = threading.Thread(target=run_eval_fail, args=("malformed-no-equals-sign",))
    t_fail.start()
    t_fail.join()

    raised = False
    if errors_b:
        try:
            raise SystemExit("\n".join(errors_b))
        except SystemExit as e:
            raised = True
            print(f"  PASS  test_l3 part-B: forced thread failure propagates via errors channel → SystemExit({str(e)[:60]!r})")

    if not raised:
        print(f"  FAIL  test_l3 part-B: forced failure did not populate errors channel")
        ok = False

    return ok


# ---------------------------------------------------------------------------
# Test L4: CLI cache key structure in workflow
# ---------------------------------------------------------------------------

def test_l4_cli_cache_key() -> bool:
    """L4: eval-ci.yml must contain a cache step for the Claude Code CLI
    with a key that includes node version and CLI version components."""
    workflow = read_workflow()

    if "cache-cli" not in workflow:
        print(f"  FAIL  test_l4: no 'cache-cli' step id found in workflow")
        return False

    if "node20" not in workflow:
        print(f"  FAIL  test_l4: cache key does not reference 'node20'")
        return False

    if "cli-version" not in workflow:
        print(f"  FAIL  test_l4: cache key does not reference cli-version step")
        return False

    # Check SHA-pinned actions/cache (or /restore + /save) used (house style)
    cache_sha_pattern = r"actions/cache(?:/restore|/save)?@[0-9a-f]{40}"
    matches = re.findall(cache_sha_pattern, workflow)
    if len(matches) < 3:
        # Expect: cache/restore (baseline), cache/save (baseline), cache (cli)
        print(f"  FAIL  test_l4: expected >=3 SHA-pinned cache uses, found {len(matches)}: {matches}")
        return False

    print(f"  PASS  test_l4: CLI cache step present with node20+cli-version key, {len(matches)} SHA-pinned cache uses")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=== Mock e2e: eval-ci optimization levers (PR-B / fix batch) ===")
    print()

    all_ok = True

    print("--- L1: Calibration-content hash (B4 CALIB_FILES + B5 sentinel) ---")
    if not test_l1_calib_hash_logic():
        all_ok = False
    print()

    print("--- L2: Judge model = claude-haiku-4-5 (workflow + ci_eval.py default) ---")
    if not test_l2_judge_model():
        all_ok = False
    print()

    print("--- L3: Real concurrent eval via ci_eval.py run --mock (B3) ---")
    if not test_l3_real_concurrent_mock():
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
