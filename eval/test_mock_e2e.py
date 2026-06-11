#!/usr/bin/env python3
"""
Mock e2e test for PR-A eval-ci defect fixes.

Three assertions (per spec):
  A. Null-comparison (identical calibrations) → 0 adversarial regressions.
  B. A FIX-REQUIRED stats verdict does NOT abort the pipeline: the comment
     body is still rendered (ci_eval.py comment runs, exits 1, but output
     written before exit).
  C. Comment body includes the verdict string.

stdlib + scipy only (scipy already required by the defect-1 fix).
"""

import csv
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
STAT_TEST = os.path.join(HERE, "statistical_test.py")
CI_EVAL = os.path.join(HERE, "ci_eval.py")


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def make_csv(rows: list[dict], path: str) -> None:
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def null_comparison_csv(tmp: str) -> str:
    """CSV where baseline == candidate for 4 adv probes × 3 runs each.

    All pass_fractions will be 1.0 vs 1.0 after aggregation; diff = 0,
    which is <= 0.5, so zero regressions expected.
    """
    rows = []
    for probe_idx in range(1, 5):
        pid = f"adv{probe_idx:02d}"
        for run_idx in range(3):
            for calib in ("baseline", "candidate"):
                rows.append({
                    "probe_id": pid,
                    "calibration": calib,
                    "probe_kind": "adv",
                    "run_idx": str(run_idx),
                    "prompt_path": "",
                    "response_path": f"/fake/{calib}-{pid}-{run_idx}.txt",
                    "score_total": "5",
                    "passed": "1",
                })
    path = os.path.join(tmp, "null_comparison.csv")
    make_csv(rows, path)
    return path


def fix_required_csv(tmp: str) -> str:
    """CSV that will produce FIX-REQUIRED from statistical_test.py.

    Uses 4 q-probes with candidate clearly worse than baseline so
    Wilcoxon p >= 0.05 and Cohen's d CI lower <= 0.2 fail.
    Uses 0 adv probes (no adv regressions) to isolate q-probe failure.
    """
    rows = []
    for probe_idx in range(1, 5):
        pid = f"q{probe_idx:02d}"
        for calib, score in (("baseline", "8"), ("candidate", "2")):
            rows.append({
                "probe_id": pid,
                "calibration": calib,
                "probe_kind": "q",
                "run_idx": "0",
                "prompt_path": "",
                "response_path": f"/fake/{calib}-{pid}.txt",
                "score_total": score,
                "passed": "1" if score == "8" else "0",
            })
    path = os.path.join(tmp, "fix_required.csv")
    make_csv(rows, path)
    return path


def run_stat_test(csv_path: str) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, STAT_TEST, csv_path, "--baseline", "baseline", "--candidate", "candidate"],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


def run_comment(csv_path: str, stats_txt: str, tmp: str) -> tuple[int, str]:
    stats_file = os.path.join(tmp, "stats.txt")
    with open(stats_file, "w") as f:
        f.write(stats_txt)
    result = subprocess.run(
        [
            sys.executable, CI_EVAL, "comment",
            "--csv", csv_path,
            "--baseline", "baseline",
            "--candidate", "candidate",
            "--baseline-sha", "aabbccdd",
            "--candidate-sha", "11223344",
            "--stats-output", stats_file,
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_a_null_comparison_zero_regressions(tmp: str) -> bool:
    """Assertion A: identical calibrations → 0 adversarial regressions."""
    csv_path = null_comparison_csv(tmp)
    code, out = run_stat_test(csv_path)
    # Check the regressions count in output
    if "McNemar adv:            0 regressions" not in out:
        print(f"  FAIL  test_a: expected '0 regressions' in output")
        print(f"        output: {out[:400]}")
        return False
    print(f"  PASS  test_a: null-comparison → 0 adv regressions (as expected)")
    return True


def test_b_fix_required_does_not_abort_comment(tmp: str) -> bool:
    """Assertion B: FIX-REQUIRED verdict from stat test does not abort comment step.

    The stats step exits 1 (captured via || true in the workflow).
    ci_eval.py comment must still produce output (comment body) even when
    the stats output contains FIX-REQUIRED — the comment step runs to completion.
    """
    csv_path = fix_required_csv(tmp)
    # Simulate what the workflow does: run stats, capture output regardless of exit code
    stat_code, stat_out = run_stat_test(csv_path)

    # Stats should produce FIX-REQUIRED (q-probes fail)
    if "FIX-REQUIRED" not in stat_out:
        print(f"  FAIL  test_b setup: expected FIX-REQUIRED in stat output")
        print(f"        stat_out: {stat_out[:400]}")
        return False

    # Now run comment — it must produce output even though stats is FIX-REQUIRED
    comment_code, comment_out = run_comment(csv_path, stat_out, tmp)
    if not comment_out.strip():
        print(f"  FAIL  test_b: comment produced no output (exit={comment_code})")
        return False
    # Comment body must contain the candidate SHA heading and verdict
    if "11223344" not in comment_out:
        print(f"  FAIL  test_b: comment body does not contain candidate SHA")
        print(f"        comment_out: {comment_out[:400]}")
        return False
    print(f"  PASS  test_b: FIX-REQUIRED stats did not abort comment step (comment rendered, exit={comment_code})")
    return True


def test_c_comment_renders_verdict(tmp: str) -> bool:
    """Assertion C: comment body contains a Verdict section with the verdict text."""
    csv_path = fix_required_csv(tmp)
    stat_code, stat_out = run_stat_test(csv_path)
    comment_code, comment_out = run_comment(csv_path, stat_out, tmp)

    if "### Verdict" not in comment_out:
        print(f"  FAIL  test_c: comment body missing '### Verdict' section")
        print(f"        comment_out: {comment_out[:600]}")
        return False
    # The verdict must be one of the known verdict strings
    known_verdicts = ["APPROVE", "WARNING", "FAIL"]
    if not any(v in comment_out for v in known_verdicts):
        print(f"  FAIL  test_c: comment body verdict section contains none of {known_verdicts}")
        print(f"        comment_out: {comment_out[:600]}")
        return False
    # Extract the verdict for display
    for line in comment_out.splitlines():
        if "### Verdict" in line or "**FAIL" in line or "**APPROVE" in line or "**WARNING" in line:
            print(f"  PASS  test_c: comment renders verdict — found: {line.strip()[:80]}")
            break
    else:
        print(f"  PASS  test_c: comment renders verdict (section present)")
    return True


def main() -> int:
    print("=== Mock e2e: eval-ci defect fixes (PR-A) ===")
    print()

    all_ok = True
    with tempfile.TemporaryDirectory() as tmp:
        print("--- Assertion A: null-comparison → 0 adv regressions ---")
        if not test_a_null_comparison_zero_regressions(tmp):
            all_ok = False
        print()

        print("--- Assertion B: FIX-REQUIRED stats does not abort comment step ---")
        if not test_b_fix_required_does_not_abort_comment(tmp):
            all_ok = False
        print()

        print("--- Assertion C: comment body renders verdict ---")
        if not test_c_comment_renders_verdict(tmp):
            all_ok = False
        print()

    if all_ok:
        print("mock e2e: ALL PASS")
    else:
        print("mock e2e: FAILURES DETECTED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
