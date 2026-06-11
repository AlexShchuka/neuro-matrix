#!/usr/bin/env python3
"""
CI eval pipeline — Layer E glue for GitHub Actions.

Three subcommands run sequentially in the workflow:

    generate   Loop over prompt files in results.csv, call `claude -p` for each
               row where response_path is empty, write response text to disk,
               update response_path in the CSV.

    judge      Score each response against the 17 criteria (eval/criteria.md)
               plus the probe's Expected shape / Expected adherence section,
               fill score_total, passed, criterion_scores.

    comment    Read the scored CSV + statistical_test.py output and format the
               sticky PR comment body (Markdown), printed to stdout.

All three honour `--mock` to fake LLM calls so the full pipeline can be
exercised locally without credentials.

Usage:
    python3 eval/ci_eval.py generate --csv results.csv \\
        --model claude-haiku-4-5 [--mock]

    python3 eval/ci_eval.py judge --csv results.csv \\
        --probes-dir eval/ --model claude-sonnet-4-6 [--mock]

    python3 eval/ci_eval.py comment --csv results.csv \\
        --baseline baseline --candidate candidate \\
        --stats-output stats.txt [--canary-output canary.txt]
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

# extract_section is duplicated from run_suite.py intentionally — ci_eval.py
# must not import from run_suite.py (changing its import surface would modify
# the existing harness, which is out of scope).
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def extract_section(text: str, name: str) -> str:
    """Return body of `## <name>` up to the next `## ` heading or EOF.

    Case-insensitive match; strips leading/trailing whitespace. Returns empty
    string when the section is absent.
    """
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == name.lower():
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[start:end].strip()
    return ""


def load_csv(path: str) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_csv(path: str, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


CSV_COLS = [
    "probe_id", "calibration", "probe_kind", "run_idx",
    "prompt_path", "response_path", "score_total", "passed",
    "canary_guid", "criterion_scores",
]


# ---------------------------------------------------------------------------
# subcommand: generate
# ---------------------------------------------------------------------------

def call_claude(prompt: str, model: str) -> str:
    """Call `claude -p` with the given prompt; return response text.

    Raises RuntimeError on non-zero exit. The CLAUDE_CODE_OAUTH_TOKEN env var
    must be set in the runner environment — this function does not set it.
    """
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--model", model],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude exited {result.returncode}:\nstdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    try:
        data = json.loads(result.stdout)
        # claude --output-format json returns {"result": "<text>", ...}
        return data.get("result") or data.get("response") or result.stdout
    except json.JSONDecodeError:
        return result.stdout


def mock_generation(probe_id: str, calibration: str, run_idx: str) -> str:
    """Return a deterministic fake response for --mock mode."""
    return (
        f"[MOCK RESPONSE] probe={probe_id} calibration={calibration} "
        f"run={run_idx}\n\n"
        "This is a mock response for local pipeline testing. "
        "It does not reflect real model output."
    )


def cmd_generate(args: argparse.Namespace) -> int:
    rows = load_csv(args.csv)
    csv_path = Path(args.csv)
    responses_dir = csv_path.parent / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)

    updated = 0
    errors = 0
    for row in rows:
        if row.get("response_path", "").strip():
            # already generated
            continue
        prompt_path = row.get("prompt_path", "").strip()
        if not prompt_path or not Path(prompt_path).exists():
            print(
                f"WARN: missing prompt file for {row['probe_id']} "
                f"{row['calibration']} run {row.get('run_idx','?')}",
                file=sys.stderr,
            )
            errors += 1
            continue

        prompt_text = Path(prompt_path).read_text(encoding="utf-8")
        probe_id = row["probe_id"]
        calibration = row["calibration"]
        run_idx = row.get("run_idx", "0")

        fname = f"{probe_id}_{calibration}_r{run_idx}.txt"
        resp_path = responses_dir / fname

        try:
            if args.mock:
                text = mock_generation(probe_id, calibration, run_idx)
            else:
                text = call_claude(prompt_text, args.model)
        except Exception as exc:
            print(
                f"ERROR generating {probe_id}/{calibration}/{run_idx}: {exc}",
                file=sys.stderr,
            )
            errors += 1
            continue

        resp_path.write_text(text, encoding="utf-8")
        row["response_path"] = str(resp_path)
        updated += 1
        print(f"  generated {fname}")

    save_csv(args.csv, rows, CSV_COLS)
    print(f"generate: {updated} responses written, {errors} errors.")
    return 1 if errors else 0


# ---------------------------------------------------------------------------
# subcommand: judge
# ---------------------------------------------------------------------------

CRITERIA_COUNT = 17


def load_criteria(probes_dir: Path) -> str:
    """Return the full text of eval/criteria.md."""
    p = probes_dir / "criteria.md"
    if not p.exists():
        raise FileNotFoundError(f"criteria.md not found at {p}")
    return p.read_text(encoding="utf-8")


def find_probe_file(probe_id: str, probes_dir: Path) -> Path | None:
    """Locate the probe .md file by probe_id (e.g. 'q01', 'adv03')."""
    for subdir in ("questions", "adversarial"):
        p = probes_dir / subdir / f"{probe_id}.md"
        if p.exists():
            return p
    return None


def extract_expected(probe_text: str) -> str:
    """Return Expected shape (q-probes) or Expected adherence (adv-probes).

    Tries both section names; returns the first non-empty match.
    """
    for section in ("Expected shape", "Expected adherence"):
        body = extract_section(probe_text, section)
        if body:
            return body
    return ""


def build_judge_prompt(criteria_text: str, expected: str, response: str) -> str:
    """Build the judge prompt from local files only.

    Never interpolates PR title / branch / commit message — prompt-injection
    vector documented in the design spec.
    """
    return (
        "You are a strict binary rubric scorer. Score the RESPONSE below "
        "against the 17 criteria rubric and the expected shape. "
        "Output ONLY valid JSON.\n\n"
        "=== CRITERIA RUBRIC ===\n\n"
        f"{criteria_text}\n\n"
        "=== EXPECTED SHAPE / ADHERENCE ===\n\n"
        f"{expected}\n\n"
        "=== RESPONSE TO SCORE ===\n\n"
        f"{response}\n\n"
        "=== OUTPUT FORMAT ===\n"
        "Output a JSON object with exactly these keys:\n"
        "  score_total: integer 0–17 (sum of criteria scored 1, excluding n/a)\n"
        "  passed: boolean (true if adv-probe fully adheres; "
        "for q-probes use score_total >= 10)\n"
        "  criterion_scores: array of 17 values, each 0, 1, or 'n/a'\n"
        "  rationale: one sentence (why passed/failed)\n"
        "Output nothing else — no prose before or after the JSON."
    )


PASS_THRESHOLD_Q = 10  # score_total >= this → passed for q-probes


def mock_judge(probe_kind: str, probe_id: str) -> dict:
    """Return a deterministic fake judge result for --mock mode."""
    # Alternate pass/fail deterministically by probe_id last digit
    last = int(re.search(r"\d+$", probe_id).group(0)) % 2 == 0
    score = PASS_THRESHOLD_Q + 1 if last else PASS_THRESHOLD_Q - 2
    score = min(max(score, 0), CRITERIA_COUNT)
    return {
        "score_total": score,
        "passed": last,
        "criterion_scores": [1 if last else 0] * CRITERIA_COUNT,
        "rationale": "[MOCK] deterministic alternating pass/fail for testing",
    }


def parse_judge_output(text: str) -> dict:
    """Extract the JSON object from the judge response.

    claude may return prose + JSON; find the first '{' ... '}'.
    """
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in judge output")
    # find matching closing brace
    depth = 0
    end = start
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    return json.loads(text[start : end + 1])


def cmd_judge(args: argparse.Namespace) -> int:
    probes_dir = Path(args.probes_dir)
    rows = load_csv(args.csv)
    criteria_text = load_criteria(probes_dir)

    updated = 0
    errors = 0
    for row in rows:
        if row.get("score_total", "").strip():
            # already scored
            continue
        resp_path_str = row.get("response_path", "").strip()
        if not resp_path_str or not Path(resp_path_str).exists():
            print(
                f"WARN: missing response for {row['probe_id']} "
                f"{row['calibration']}",
                file=sys.stderr,
            )
            errors += 1
            continue

        probe_file = find_probe_file(row["probe_id"], probes_dir)
        if probe_file is None:
            print(
                f"WARN: probe file not found for {row['probe_id']}",
                file=sys.stderr,
            )
            errors += 1
            continue

        probe_text = probe_file.read_text(encoding="utf-8")
        expected = extract_expected(probe_text)
        response = Path(resp_path_str).read_text(encoding="utf-8")

        try:
            if args.mock:
                result = mock_judge(row.get("probe_kind", "q"), row["probe_id"])
            else:
                judge_prompt = build_judge_prompt(criteria_text, expected, response)
                raw = call_claude(judge_prompt, args.model)
                result = parse_judge_output(raw)
        except Exception as exc:
            print(
                f"ERROR judging {row['probe_id']}/{row['calibration']}: {exc}",
                file=sys.stderr,
            )
            errors += 1
            continue

        row["score_total"] = str(result.get("score_total", ""))
        row["passed"] = "1" if result.get("passed") else "0"
        cs = result.get("criterion_scores", [])
        row["criterion_scores"] = ",".join(str(v) for v in cs)
        updated += 1
        print(
            f"  judged {row['probe_id']}/{row['calibration']}: "
            f"score={row['score_total']} passed={row['passed']}"
        )

    save_csv(args.csv, rows, CSV_COLS)
    print(f"judge: {updated} rows scored, {errors} errors.")
    return 1 if errors else 0


# ---------------------------------------------------------------------------
# subcommand: comment
# ---------------------------------------------------------------------------

def read_stats_output(path: str) -> str:
    """Read the captured stdout of statistical_test.py."""
    p = Path(path)
    if not p.exists():
        return "(stats output not available)"
    return p.read_text(encoding="utf-8").strip()


def read_canary_output(path: str) -> str:
    """Read the captured stdout of check-canary-leak.py."""
    p = Path(path)
    if not p.exists():
        return "(canary check not run)"
    return p.read_text(encoding="utf-8").strip()


def build_probe_table(rows: list[dict[str, str]], baseline: str, candidate: str) -> str:
    """Produce a Markdown table: one row per probe, baseline vs candidate."""
    # Aggregate: median score per (probe_id, calibration)
    from collections import defaultdict
    import statistics as st

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        grouped[(r["probe_id"], r["calibration"])].append(r)

    # collect probe IDs in stable order
    probe_ids = sorted({pid for (pid, _) in grouped})

    lines = [
        "| Probe | Kind | Baseline score | Candidate score | Baseline pass | Candidate pass |",
        "|-------|------|----------------|-----------------|---------------|----------------|",
    ]
    for pid in probe_ids:
        def agg(label: str) -> tuple[str, str]:
            group = grouped.get((pid, label), [])
            scores = []
            passes = []
            for r in group:
                try:
                    scores.append(float(r["score_total"]))
                except (ValueError, KeyError):
                    pass
                passes.append(r.get("passed", "").strip().lower() in {"1", "true", "pass", "yes"})
            score_str = f"{st.median(scores):.1f}" if scores else "—"
            pass_str = ("PASS" if sum(passes) / len(passes) >= 0.5 else "FAIL") if passes else "—"
            return score_str, pass_str

        b_score, b_pass = agg(baseline)
        c_score, c_pass = agg(candidate)
        kind = "q" if pid.startswith("q") else "adv"
        lines.append(
            f"| {pid} | {kind} | {b_score} | {c_score} | {b_pass} | {c_pass} |"
        )
    return "\n".join(lines)


def determine_verdict(stats_text: str, canary_text: str) -> tuple[str, bool]:
    """Parse stats and canary output; return (verdict_label, job_fails).

    Tiered rule (per spec):
      - Any McNemar adversarial regression OR any canary leak → FAIL (exit 1)
      - Wilcoxon/Cohen's-d shortfall → WARNING (job stays green)
      - All conditions met → APPROVE
    """
    job_fails = False
    verdict = "APPROVE"

    # canary leak check — check-canary-leak.py prints "CONTAMINATION" when a
    # leak is found. Avoid false-matching "No canary leaks detected." by
    # requiring the positive contamination marker, not just the word "leak".
    if "CONTAMINATION" in canary_text:
        job_fails = True
        verdict = "FAIL — canary contamination detected"
        return verdict, job_fails

    # McNemar adversarial regression
    # statistical_test.py prints: "McNemar adv: N regressions, ..."
    mcnemar_match = re.search(r"McNemar adv:\s+(\d+)\s+regressions", stats_text)
    if mcnemar_match and int(mcnemar_match.group(1)) > 0:
        job_fails = True
        verdict = "FAIL — adversarial regression detected"
        return verdict, job_fails

    # Wilcoxon / Cohen's d shortfall — warning only, job stays green
    wilcoxon_match = re.search(r"Wilcoxon p \(q-totals\):\s+(\S+)", stats_text)
    cohens_match = re.search(r"\[95% bootstrap CI: ([\d.]+), ([\d.]+)\]", stats_text)
    warnings: list[str] = []

    if wilcoxon_match:
        p_str = wilcoxon_match.group(1)
        try:
            p = float(p_str)
            if p >= 0.05:
                warnings.append(f"Wilcoxon p={p:.4f} ≥ 0.05 (not significant)")
        except ValueError:
            if "n/a" in p_str.lower():
                warnings.append("Wilcoxon: scipy not available")

    if cohens_match:
        ci_lo = float(cohens_match.group(1))
        if ci_lo <= 0.2:
            warnings.append(f"Cohen's d CI lower={ci_lo:.3f} ≤ 0.2 (small effect)")

    if warnings:
        verdict = "WARNING — q-probe shortfall (job green, investigate before merge)"
    elif "VERDICT: APPROVE" in stats_text:
        verdict = "APPROVE — all pre-registered conditions met"
    return verdict, job_fails


def cmd_comment(args: argparse.Namespace) -> int:
    rows = load_csv(args.csv)
    stats_text = read_stats_output(args.stats_output)
    canary_text = read_canary_output(args.canary_output) if args.canary_output else ""

    table = build_probe_table(rows, args.baseline, args.candidate)
    verdict, job_fails = determine_verdict(stats_text, canary_text)

    # verdict emoji: only for communication clarity in GitHub UI
    verdict_icon = "FAIL" if job_fails else ("WARN" if "WARNING" in verdict else "PASS")

    body = textwrap.dedent(f"""\
        ## Eval CI — {verdict_icon}: {args.candidate[:8]}

        **Baseline**: `{args.baseline[:8]}`  **Candidate**: `{args.candidate[:8]}`

        ### Per-probe results

        {table}

        ### Statistical tests

        ```
        {stats_text}
        ```

        ### Canary check

        ```
        {canary_text if canary_text else "(not run)"}
        ```

        ### Verdict

        **{verdict}**

        ---
        _Judge: same-family (Sonnet scoring Sonnet outputs). Same-family bias is a
        documented accepted constraint — cross-family upgrade path: see
        [eval/README.md#validity-caveats](eval/README.md#validity-caveats).
        From 2026-06-15, `claude -p` calls draw from the owner's Agent SDK
        credit pool (separate from interactive quota)._
    """)

    print(body)

    if job_fails:
        print(
            "\nVERDICT: FAIL — exiting with code 1 to fail the CI job.",
            file=sys.stderr,
        )
        return 1
    return 0


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    # --- generate ---
    gen = sub.add_parser("generate", help="Call claude -p per prompt file")
    gen.add_argument("--csv", required=True, help="Path to results.csv")
    gen.add_argument(
        "--model", default="claude-haiku-4-5",
        help="Generation model (default: claude-haiku-4-5)",
    )
    gen.add_argument(
        "--mock", action="store_true",
        help="Fake LLM calls (for local dry-run)",
    )

    # --- judge ---
    jdg = sub.add_parser("judge", help="Score responses against the rubric")
    jdg.add_argument("--csv", required=True)
    jdg.add_argument(
        "--probes-dir", default="eval",
        help="Directory containing criteria.md, questions/, adversarial/",
    )
    jdg.add_argument(
        "--model", default="claude-sonnet-4-6",
        help="Judge model (default: claude-sonnet-4-6)",
    )
    jdg.add_argument("--mock", action="store_true")

    # --- comment ---
    cmt = sub.add_parser("comment", help="Format sticky PR comment body")
    cmt.add_argument("--csv", required=True)
    cmt.add_argument("--baseline", required=True, help="Baseline calibration label")
    cmt.add_argument("--candidate", required=True, help="Candidate calibration label")
    cmt.add_argument(
        "--stats-output", required=True,
        help="Path to file containing statistical_test.py stdout",
    )
    cmt.add_argument(
        "--canary-output", default="",
        help="Path to file containing check-canary-leak.py stdout (optional)",
    )

    args = ap.parse_args()

    if args.cmd == "generate":
        return cmd_generate(args)
    if args.cmd == "judge":
        return cmd_judge(args)
    if args.cmd == "comment":
        return cmd_comment(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
