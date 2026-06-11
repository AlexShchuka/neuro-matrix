#!/usr/bin/env python3
"""
CI eval pipeline — Layer E glue for GitHub Actions.

Subcommands:

    run        Full pipeline: materialise → generate → judge for one calibration
               (baseline or candidate), fully parallel, with prompt-cache warm-up.
               Writes a self-contained CSV ready for statistical_test.py.

               Usage:
                   python3 eval/ci_eval.py run \\
                       --ref <sha>=<label> \\
                       --probes questions,adversarial \\
                       --k 3 \\
                       --out results.csv \\
                       --gen-model claude-haiku-4-5 \\
                       --judge-model claude-sonnet-4-6 \\
                       [--mock] [--prompts-dir /tmp/prompts]

    generate   (legacy) Loop over prompt files in results.csv, call `claude -p`
               for each row where response_path is empty, write response text to
               disk, update response_path in the CSV.

    judge      (legacy) Score each response against the 17 criteria.

    comment    Read the scored CSV + statistical_test.py output and format the
               sticky PR comment body (Markdown), printed to stdout.

All subcommands honour `--mock` to fake LLM calls so the full pipeline can be
exercised locally without credentials.

Prompt-caching design (V-b verified 2026-06-11):
    `claude -p` with `--system-prompt <text>` + `--output-format json` sends
    the calibration as the system turn. The Anthropic API caches large identical
    system prompts automatically (cache_creation_input_tokens on first call,
    cache_read_input_tokens on subsequent calls). A warm-up call per calibration
    is issued before the parallel burst to prime the cache so all pending cells
    share one cached 60 KB prefix.

Parallelism design (V-c):
    ThreadPoolExecutor with max_workers = total pending cells (full fan-out).
    Override with EVAL_MAX_WORKERS env var for emergency throttling.
    Retryable errors (overload / 429-shaped) get one retry with 5 s backoff.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    "prompt_path", "calib_path", "response_path",
    "score_total", "passed", "canary_guid", "criterion_scores",
]

# Columns present in legacy CSVs (no calib_path / criterion_scores).
# save_csv uses extrasaction="ignore" so missing keys are fine.
LEGACY_CSV_COLS = [
    "probe_id", "calibration", "probe_kind", "run_idx",
    "prompt_path", "response_path", "score_total", "passed",
    "canary_guid", "criterion_scores",
]


# ---------------------------------------------------------------------------
# LLM call — caching-aware split call
# ---------------------------------------------------------------------------

# Errors whose text indicates the request is retryable.
_RETRYABLE_PATTERNS = re.compile(
    r"overload|rate.limit|429|503|unavailable|try.again",
    re.IGNORECASE,
)

CALL_TIMEOUT_SEC = 180
RETRY_BACKOFF_SEC = 5


def call_claude_split(
    system_prompt: str,
    user_prompt: str,
    model: str,
    *,
    timeout: int = CALL_TIMEOUT_SEC,
) -> str:
    """Call `claude -p` with separate system/user prompts; return response text.

    Passes the calibration as --system-prompt so the Anthropic API can cache
    the large 60 KB prefix. The user_prompt is the small per-probe text.

    CLI contract (verified live 2026-06-11, @anthropic-ai/claude-code):
      claude -p "<user>" --system-prompt "<system>" --output-format json
              --model <model>
      JSON response: {"type":"result","subtype":"success","result":"<text>",...}
      usage.cache_read_input_tokens > 0 on subsequent calls with same system.

    Raises RuntimeError on non-zero exit. One retry on retryable patterns.
    """
    cmd = [
        "claude", "-p", user_prompt,
        "--system-prompt", system_prompt,
        "--output-format", "json",
        "--model", model,
    ]
    for attempt in range(2):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            if attempt == 0:
                time.sleep(RETRY_BACKOFF_SEC)
                continue
            raise RuntimeError(f"claude timed out after {timeout}s")

        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                return data.get("result") or result.stdout
            except json.JSONDecodeError:
                return result.stdout

        combined = result.stdout + result.stderr
        if attempt == 0 and _RETRYABLE_PATTERNS.search(combined):
            time.sleep(RETRY_BACKOFF_SEC)
            continue

        raise RuntimeError(
            f"claude exited {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    raise RuntimeError("claude failed after retry")


def call_claude(prompt: str, model: str) -> str:
    """Call `claude -p` with a single concatenated prompt (legacy path).

    Verified CLI contract (live call, 2026-06-11, @anthropic-ai/claude-code):
      claude -p "<prompt>" --output-format json --model claude-haiku-4-5
      -> JSON: {"type":"result","subtype":"success","result":"<text>",...}
      The response text lives in the top-level "result" key.
      Model ids accepted: claude-haiku-4-5 (generation), claude-sonnet-4-6 (judge).
    """
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--model", model],
        capture_output=True,
        text=True,
        timeout=CALL_TIMEOUT_SEC,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude exited {result.returncode}:\nstdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    try:
        data = json.loads(result.stdout)
        return data.get("result") or result.stdout
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


# ---------------------------------------------------------------------------
# subcommand: run  (unified parallel pipeline)
# ---------------------------------------------------------------------------

def _run_suite_materialize(
    ref: str,
    label: str,
    probes: str,
    k: int,
    out_csv: str,
    prompts_dir: str,
) -> int:
    """Call run_suite.py to materialise prompts and write the stub CSV."""
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "run_suite.py"),
        "--refs", f"{ref}={label}",
        "--probes", probes,
        "--k", str(k),
        "--out", out_csv,
        "--prompts-dir", prompts_dir,
    ]
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


def _generate_one(
    row: dict[str, str],
    model: str,
    responses_dir: Path,
    mock: bool,
    idx: int,
    total: int,
) -> tuple[dict[str, str], str | None]:
    """Generate response for one CSV row. Returns (updated_row, error_str|None)."""
    prompt_path = row.get("prompt_path", "").strip()
    calib_path = row.get("calib_path", "").strip()
    probe_id = row["probe_id"]
    calibration = row["calibration"]
    run_idx = row.get("run_idx", "0")
    label = f"{probe_id}/{calibration}/r{run_idx}"

    t0 = time.monotonic()
    try:
        if mock:
            text = mock_generation(probe_id, calibration, run_idx)
        elif calib_path and Path(calib_path).exists() and Path(prompt_path).exists():
            # Caching path: system = calibration, user = probe prompt
            system_text = Path(calib_path).read_text(encoding="utf-8")
            user_text = Path(prompt_path).read_text(encoding="utf-8")
            text = call_claude_split(system_text, user_text, model)
        elif prompt_path and Path(prompt_path).exists():
            # Fallback: legacy concatenated prompt
            text = call_claude(Path(prompt_path).read_text(encoding="utf-8"), model)
        else:
            elapsed = time.monotonic() - t0
            return row, f"missing prompt file for {label} ({elapsed:.1f}s)"

        fname = f"{probe_id}_{calibration}_r{run_idx}.txt"
        resp_path = responses_dir / fname
        resp_path.write_text(text, encoding="utf-8")
        row = dict(row)
        row["response_path"] = str(resp_path)
        elapsed = time.monotonic() - t0
        print(f"  [{idx}/{total}] generate {label} -> ok ({elapsed:.1f}s)")
        return row, None

    except Exception as exc:
        elapsed = time.monotonic() - t0
        return row, f"{label} ({elapsed:.1f}s): {exc}"


def _judge_one(
    row: dict[str, str],
    model: str,
    criteria_system: str,
    mock: bool,
    idx: int,
    total: int,
) -> tuple[dict[str, str], str | None]:
    """Judge one scored response. Returns (updated_row, error_str|None)."""
    probe_id = row["probe_id"]
    calibration = row["calibration"]
    run_idx = row.get("run_idx", "0")
    label = f"{probe_id}/{calibration}/r{run_idx}"

    resp_path_str = row.get("response_path", "").strip()
    t0 = time.monotonic()
    try:
        if mock:
            result = mock_judge(probe_id)
        else:
            if not resp_path_str or not Path(resp_path_str).exists():
                return row, f"missing response for {label}"
            probe_file = find_probe_file(probe_id, SCRIPT_DIR)
            if probe_file is None:
                return row, f"probe file not found for {probe_id}"
            probe_text = probe_file.read_text(encoding="utf-8")
            expected = extract_expected(probe_text)
            response = Path(resp_path_str).read_text(encoding="utf-8")
            # Judge call: system = criteria rubric (cached), user = expected + response
            user_prompt = build_judge_user_prompt(expected, response)
            raw = call_claude_split(criteria_system, user_prompt, model)
            result = parse_judge_output(raw)

        row = dict(row)
        row["score_total"] = str(result.get("score_total", ""))
        row["passed"] = "1" if result.get("passed") else "0"
        cs = result.get("criterion_scores", [])
        row["criterion_scores"] = ",".join(str(v) for v in cs)
        elapsed = time.monotonic() - t0
        print(
            f"  [{idx}/{total}] judge {label} -> "
            f"score={row['score_total']} passed={row['passed']} ({elapsed:.1f}s)"
        )
        return row, None

    except Exception as exc:
        elapsed = time.monotonic() - t0
        return row, f"{label} ({elapsed:.1f}s): {exc}"


def _warmup_call(system_text: str, model: str, label: str) -> None:
    """Prime the cache for a calibration by making one minimal call."""
    print(f"  [warmup] {label} priming cache ...")
    t0 = time.monotonic()
    try:
        call_claude_split(system_text, "respond with: ready", model)
        elapsed = time.monotonic() - t0
        print(f"  [warmup] {label} cached ({elapsed:.1f}s)")
    except Exception as exc:
        elapsed = time.monotonic() - t0
        print(f"  [warmup] {label} failed ({elapsed:.1f}s): {exc}", file=sys.stderr)


def cmd_run(args: argparse.Namespace) -> int:
    """Unified parallel pipeline: materialise → warmup → generate → judge."""
    ref_pair = args.ref.split("=", 1)
    if len(ref_pair) != 2:
        print("--ref must be <git-ref>=<label>", file=sys.stderr)
        return 2
    ref, label = ref_pair

    prompts_dir = args.prompts_dir or tempfile.mkdtemp(prefix="eval-prompts-")
    out_csv = args.out

    # --- Materialise ---
    print(f"[run] materialising prompts for {label} ...")
    rc = _run_suite_materialize(
        ref=ref,
        label=label,
        probes=args.probes,
        k=args.k,
        out_csv=out_csv,
        prompts_dir=prompts_dir,
    )
    if rc != 0:
        print(f"[run] run_suite.py failed (rc={rc})", file=sys.stderr)
        return rc

    rows = load_csv(out_csv)
    pending_gen = [r for r in rows if not r.get("response_path", "").strip()]
    total_gen = len(pending_gen)

    if not pending_gen:
        print("[run] all responses already generated — skipping generate phase.")
    else:
        responses_dir = Path(out_csv).parent / "responses"
        responses_dir.mkdir(parents=True, exist_ok=True)

        # --- Warm-up: prime cache per calibration ---
        if not args.mock:
            calib_paths: dict[str, str] = {}
            for r in pending_gen:
                cp = r.get("calib_path", "").strip()
                cal = r["calibration"]
                if cp and cal not in calib_paths:
                    calib_paths[cal] = cp
            for cal, cp in calib_paths.items():
                system_text = Path(cp).read_text(encoding="utf-8")
                _warmup_call(system_text, args.gen_model, cal)

        # --- Parallel generate ---
        max_workers = int(os.environ.get("EVAL_MAX_WORKERS", str(total_gen)))
        print(f"[run] generating {total_gen} responses (workers={max_workers}) ...")
        gen_errors: list[str] = []
        updated_rows: dict[int, dict[str, str]] = {}

        # Build index map: row identity → position in rows list
        row_index: dict[int, int] = {}
        pending_idx = 0
        for i, r in enumerate(rows):
            if not r.get("response_path", "").strip():
                row_index[pending_idx] = i
                pending_idx += 1

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    _generate_one, r, args.gen_model, responses_dir,
                    args.mock, idx + 1, total_gen,
                ): idx
                for idx, r in enumerate(pending_gen)
            }
            for future in as_completed(future_to_idx):
                pending_pos = future_to_idx[future]
                updated_row, err = future.result()
                if err:
                    gen_errors.append(err)
                    print(f"  ERROR generate: {err}", file=sys.stderr)
                else:
                    updated_rows[row_index[pending_pos]] = updated_row

        for pos, updated in updated_rows.items():
            rows[pos] = updated

        save_csv(out_csv, rows, CSV_COLS)
        print(f"[run] generate done: {len(updated_rows)} ok, {len(gen_errors)} errors.")

    # --- Judge phase ---
    rows = load_csv(out_csv)
    pending_judge = [r for r in rows if not r.get("score_total", "").strip()]
    total_judge = len(pending_judge)

    if not pending_judge:
        print("[run] all responses already judged — skipping judge phase.")
    else:
        probes_dir = SCRIPT_DIR
        criteria_text = load_criteria(probes_dir)

        # Build judge system prompt: static rubric only (cached across all calls).
        judge_system = build_judge_system_prompt(criteria_text)

        # Warm-up for judge model (same criteria prefix, different model).
        if not args.mock:
            _warmup_call(judge_system, args.judge_model, f"judge-rubric ({label})")

        max_workers = int(os.environ.get("EVAL_MAX_WORKERS", str(total_judge)))
        print(f"[run] judging {total_judge} responses (workers={max_workers}) ...")
        judge_errors: list[str] = []
        updated_judge: dict[int, dict[str, str]] = {}

        # Build pending-to-rows mapping
        judge_index: dict[int, int] = {}
        pending_j_idx = 0
        for i, r in enumerate(rows):
            if not r.get("score_total", "").strip():
                judge_index[pending_j_idx] = i
                pending_j_idx += 1

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    _judge_one, r, args.judge_model, judge_system,
                    args.mock, idx + 1, total_judge,
                ): idx
                for idx, r in enumerate(pending_judge)
            }
            for future in as_completed(future_to_idx):
                pending_pos = future_to_idx[future]
                updated_row, err = future.result()
                if err:
                    judge_errors.append(err)
                    print(f"  ERROR judge: {err}", file=sys.stderr)
                else:
                    updated_judge[judge_index[pending_pos]] = updated_row

        for pos, updated in updated_judge.items():
            rows[pos] = updated

        save_csv(out_csv, rows, CSV_COLS)
        print(f"[run] judge done: {len(updated_judge)} ok, {len(judge_errors)} errors.")

    incomplete = [r for r in rows if not r.get("response_path") or not r.get("score_total")]
    if incomplete:
        # Cell-level failures: generation or judge errors for individual probes.
        # Return 0 so set -euo pipefail does not abort the workflow before
        # merge/stats/canary/comment/enforce; the tiered verdict is the gate.
        # The incomplete count is printed here and surfaced in the sticky
        # comment via cmd_comment reading the CSV directly.
        print(
            f"[run] complete — {len(rows)} rows, {len(incomplete)} incomplete "
            f"(cell-level errors; tiered verdict will reflect degradation).",
            file=sys.stderr,
        )
    else:
        print(f"[run] complete — {len(rows)} rows, all ok.")
    return 0


# ---------------------------------------------------------------------------
# subcommand: generate  (legacy)
# ---------------------------------------------------------------------------

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

    save_csv(args.csv, rows, LEGACY_CSV_COLS)
    print(f"generate: {updated} responses written, {errors} errors.")
    return 1 if errors else 0


# ---------------------------------------------------------------------------
# subcommand: judge  (legacy + shared helpers)
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


def build_judge_system_prompt(criteria_text: str) -> str:
    """Static judge system prompt — cached across all pending judge calls.

    Contains only the rubric (same for every probe). The per-probe expected
    shape and the response are in the user turn (build_judge_user_prompt).
    """
    return (
        "You are a strict binary rubric scorer. Score each RESPONSE against "
        "the 17 criteria rubric below and the expected shape provided in the "
        "user turn. Output ONLY valid JSON.\n\n"
        "=== CRITERIA RUBRIC ===\n\n"
        f"{criteria_text}\n\n"
        "=== OUTPUT FORMAT ===\n"
        "Output a JSON object with exactly these keys:\n"
        "  score_total: integer 0-17 (sum of criteria scored 1, excluding n/a)\n"
        "  passed: boolean (true if adv-probe fully adheres; "
        "for q-probes use score_total >= 10)\n"
        "  criterion_scores: array of 17 values, each 0, 1, or 'n/a'\n"
        "  rationale: one sentence (why passed/failed)\n"
        "Output nothing else — no prose before or after the JSON."
    )


def build_judge_user_prompt(expected: str, response: str) -> str:
    """Per-probe user turn for the judge (not cached — differs per probe)."""
    return (
        "=== EXPECTED SHAPE / ADHERENCE ===\n\n"
        f"{expected}\n\n"
        "=== RESPONSE TO SCORE ===\n\n"
        f"{response}"
    )


def build_judge_prompt(criteria_text: str, expected: str, response: str) -> str:
    """Build the legacy single-turn judge prompt (used by cmd_judge).

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
        "  score_total: integer 0-17 (sum of criteria scored 1, excluding n/a)\n"
        "  passed: boolean (true if adv-probe fully adheres; "
        "for q-probes use score_total >= 10)\n"
        "  criterion_scores: array of 17 values, each 0, 1, or 'n/a'\n"
        "  rationale: one sentence (why passed/failed)\n"
        "Output nothing else — no prose before or after the JSON."
    )


PASS_THRESHOLD_Q = 10  # score_total >= this -> passed for q-probes


def mock_judge(probe_id: str) -> dict:
    """Return a deterministic fake judge result for --mock mode.

    Proves pipeline wiring only — not verdict logic. Always emits passed=True
    so --mock never trips the real adversarial-regression fail gate (McNemar
    requires actual regressions; mock data must not produce false positives).
    score_total alternates above/below the q-probe threshold by probe number
    to exercise both table cells without affecting the adv-pass path.
    """
    # Alternate score by probe number to exercise both score table cells.
    last_digit = int(re.search(r"\d+$", probe_id).group(0)) % 2
    score = PASS_THRESHOLD_Q + 1 if last_digit == 0 else PASS_THRESHOLD_Q - 2
    score = min(max(score, 0), CRITERIA_COUNT)
    return {
        "score_total": score,
        "passed": True,  # always pass — mock must not trigger adv-regression gate
        "criterion_scores": [1] * CRITERIA_COUNT,
        "rationale": "[MOCK] wiring test — verdict logic not exercised",
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
                result = mock_judge(row["probe_id"])
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

    save_csv(args.csv, rows, LEGACY_CSV_COLS)
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
            score_str = f"{st.median(scores):.1f}" if scores else "-"
            pass_str = ("PASS" if sum(passes) / len(passes) >= 0.5 else "FAIL") if passes else "-"
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
      - Any McNemar adversarial regression OR any canary leak -> FAIL (exit 1)
      - Wilcoxon/Cohen's-d shortfall -> WARNING (job stays green)
      - All conditions met -> APPROVE
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
                warnings.append(f"Wilcoxon p={p:.4f} >= 0.05 (not significant)")
        except ValueError:
            if "n/a" in p_str.lower():
                warnings.append("Wilcoxon: scipy not available")

    if cohens_match:
        ci_lo = float(cohens_match.group(1))
        if ci_lo <= 0.2:
            warnings.append(f"Cohen's d CI lower={ci_lo:.3f} <= 0.2 (small effect)")

    if warnings:
        verdict = "WARNING — q-probe shortfall (job green, investigate before merge)"
    elif "VERDICT: APPROVE" in stats_text:
        verdict = "APPROVE — all pre-registered conditions met"
    return verdict, job_fails


def cmd_comment(args: argparse.Namespace) -> int:
    rows = load_csv(args.csv)
    stats_text = read_stats_output(args.stats_output)
    canary_text = read_canary_output(args.canary_output) if args.canary_output else ""

    # --baseline / --candidate are the CSV calibration labels (e.g. "baseline",
    # "candidate") used for table lookup. --baseline-sha / --candidate-sha are
    # the git SHAs for the comment heading (default to the labels if not given).
    baseline_sha = getattr(args, "baseline_sha", None) or args.baseline
    candidate_sha = getattr(args, "candidate_sha", None) or args.candidate

    # Surface any incomplete cells (generate/judge cell-level failures).
    incomplete = [r for r in rows if not r.get("response_path") or not r.get("score_total")]
    incomplete_note = (
        f"\n> **{len(incomplete)} cell(s) incomplete** "
        f"(generate/judge errors — scores reflect available data only)\n"
        if incomplete else ""
    )

    table = build_probe_table(rows, args.baseline, args.candidate)
    verdict, job_fails = determine_verdict(stats_text, canary_text)

    # verdict tag: text token for GitHub UI heading
    verdict_icon = "FAIL" if job_fails else ("WARN" if "WARNING" in verdict else "PASS")

    body = textwrap.dedent(f"""\
        ## Eval CI -- {verdict_icon}: {candidate_sha[:8]}

        **Baseline**: `{baseline_sha[:8]}`  **Candidate**: `{candidate_sha[:8]}`
        {incomplete_note}
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
        _Judge: same-family (Haiku scoring Haiku outputs). Same-family bias is a
        documented accepted constraint — cross-family upgrade path: see
        [eval/README.md#validity-caveats](eval/README.md#validity-caveats)._
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

    # --- run (unified parallel pipeline) ---
    run_p = sub.add_parser("run", help="Full pipeline: materialise → generate → judge")
    run_p.add_argument(
        "--ref", required=True,
        help="<git-ref>=<label> (e.g. abc123=baseline)",
    )
    run_p.add_argument("--probes", default="questions,adversarial")
    run_p.add_argument("--k", type=int, default=3, help="Runs per probe (default: 3)")
    run_p.add_argument("--out", required=True, help="Output CSV path")
    run_p.add_argument(
        "--gen-model", default="claude-haiku-4-5",
        help="Generation model (default: claude-haiku-4-5)",
    )
    run_p.add_argument(
        "--judge-model", default="claude-sonnet-4-6",
        help="Judge model (default: claude-sonnet-4-6)",
    )
    run_p.add_argument(
        "--prompts-dir", default="",
        help="Directory for materialised prompt files (default: tmpdir)",
    )
    run_p.add_argument("--mock", action="store_true", help="Fake LLM calls")

    # --- generate (legacy) ---
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

    # --- judge (legacy) ---
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
    cmt.add_argument(
        "--baseline", required=True,
        help="Baseline calibration label (must match CSV 'calibration' column, e.g. 'baseline')",
    )
    cmt.add_argument(
        "--candidate", required=True,
        help="Candidate calibration label (must match CSV 'calibration' column, e.g. 'candidate')",
    )
    cmt.add_argument(
        "--baseline-sha", default="",
        help="Baseline git SHA for comment heading (optional; defaults to --baseline value)",
    )
    cmt.add_argument(
        "--candidate-sha", default="",
        help="Candidate git SHA for comment heading (optional; defaults to --candidate value)",
    )
    cmt.add_argument(
        "--stats-output", required=True,
        help="Path to file containing statistical_test.py stdout",
    )
    cmt.add_argument(
        "--canary-output", default="",
        help="Path to file containing check-canary-leak.py stdout (optional)",
    )

    args = ap.parse_args()

    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "generate":
        return cmd_generate(args)
    if args.cmd == "judge":
        return cmd_judge(args)
    if args.cmd == "comment":
        return cmd_comment(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
