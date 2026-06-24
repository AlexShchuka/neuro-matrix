#!/usr/bin/env python3
"""Canary-leak check on Layer E eval responses.

Each probe in eval/questions/ and eval/adversarial/ carries a unique GUID in
its `## Canary` section. The GUID is recorded in results.csv (column
canary_guid) by run_suite.py. The probe's prompt does NOT contain the GUID —
only the probe file does. If a response contains the GUID, the model read
the probe file (e.g. via repo grep), not just the prompt body. That is
hard contamination and must fail the eval.

Usage:
    python3 scripts/check-canary-leak.py path/to/results.csv

Exit code: 0 if no leaks, 1 if any leak is found.
"""

import argparse
import csv
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results_csv")
    args = ap.parse_args()

    leaks: list[tuple[str, str, str, str]] = []
    missing_responses = 0
    checked = 0

    with open(args.results_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            guid = (row.get("canary_guid") or "").strip()
            resp = (row.get("response_path") or "").strip()
            if not guid or not resp:
                continue
            p = Path(resp)
            if not p.exists():
                missing_responses += 1
                continue
            checked += 1
            text = p.read_text(encoding="utf-8", errors="replace")
            if guid in text:
                leaks.append((
                    row.get("probe_id", ""),
                    row.get("calibration", ""),
                    row.get("run_idx", "0"),
                    resp,
                ))

    print(f"Checked {checked} response(s); {missing_responses} response_path entries missing on disk.")

    if checked == 0 and missing_responses > 0:
        print(
            f"VACUOUS GREEN — 0 responses checked but {missing_responses} "
            "response_path entries missing on disk; nothing was actually verified."
        )
        return 1

    if not leaks:
        print("No canary leaks detected.")
        return 0

    print(f"CONTAMINATION — {len(leaks)} canary leak(s):")
    for pid, calib, run, resp in leaks:
        print(f"  - probe={pid}  calibration={calib}  run={run}  response={resp}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
