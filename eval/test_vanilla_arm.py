#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
RUN_SUITE = os.path.join(_HERE, "run_suite.py")
STAT_TEST = os.path.join(_HERE, "statistical_test.py")

_st_spec = importlib.util.spec_from_file_location("statistical_test", STAT_TEST)
st = importlib.util.module_from_spec(_st_spec)
_st_spec.loader.exec_module(st)


def _run_suite(refs_str: str, prompts_dir: str, out_csv: str) -> tuple[int, list[dict]]:
    result = subprocess.run(
        [
            sys.executable, RUN_SUITE,
            "--refs", refs_str,
            "--probes", "questions",
            "--k", "1",
            "--out", out_csv,
            "--prompts-dir", prompts_dir,
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    if not os.path.exists(out_csv):
        return result.returncode, []
    with open(out_csv, newline="", encoding="utf-8") as f:
        return result.returncode, list(csv.DictReader(f))


def test_vanilla_arm_not_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        rc, rows = _run_suite(
            "vanilla=vanilla",
            os.path.join(tmp, "prompts"),
            os.path.join(tmp, "results.csv"),
        )
        assert rc == 0, f"run_suite exited {rc}"
        assert len(rows) > 0, "vanilla arm produced zero rows — was skipped"
        assert all(r["calibration"] == "vanilla" for r in rows)


def test_vanilla_arm_calib_file_is_empty():
    with tempfile.TemporaryDirectory() as tmp:
        _rc, rows = _run_suite(
            "vanilla=vanilla",
            os.path.join(tmp, "prompts"),
            os.path.join(tmp, "results.csv"),
        )
        assert len(rows) > 0, "vanilla arm produced zero rows — was skipped"
        for row in rows:
            calib_path = row["calib_path"]
            assert calib_path, f"calib_path empty for row {row['probe_id']}"
            content = Path(calib_path).read_text(encoding="utf-8")
            assert content == "", (
                f"vanilla calib file must be empty, got: {content[:60]!r}"
            )


def test_ordinary_ref_empty_still_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        _rc, rows = _run_suite(
            "deadbeef000000000000000000000000deadbeef=baseline",
            os.path.join(tmp, "prompts"),
            os.path.join(tmp, "results.csv"),
        )
        assert len(rows) == 0, (
            f"non-vanilla empty calibration must be skipped, got {len(rows)} rows"
        )


def test_vanilla_pairs_reach_statistical_test():
    vanilla_row = {
        "probe_id": "q01",
        "calibration": "vanilla",
        "probe_kind": "q",
        "run_idx": "0",
        "score_total": "8",
        "passed": "0",
    }
    candidate_row = {
        "probe_id": "q01",
        "calibration": "candidate",
        "probe_kind": "q",
        "run_idx": "0",
        "score_total": "12",
        "passed": "1",
    }
    agg = st.aggregate_runs([vanilla_row, candidate_row])
    assert ("q01", "vanilla") in agg, "vanilla arm missing from aggregated results"
    assert ("q01", "candidate") in agg

    q_b, q_c = st.collect_pairs(agg, "vanilla", "candidate", "q")
    assert len(q_b) == 1, f"expected 1 paired probe, got {len(q_b)}"
    assert q_b[0] == 8.0
    assert q_c[0] == 12.0


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__} (exception): {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
