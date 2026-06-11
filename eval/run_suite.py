#!/usr/bin/env python3
"""
Plugin calibration A/B harness — Layer E.

Constructs evaluator prompts for each (probe × calibration × run) cell, intended
to be fed to Claude (via API, CLI, or sub-agent) for response generation. The
runner does not call an LLM itself — that step is environment-specific. It
materialises prompts and tracks results in a CSV ready for the downstream
statistical_test.py.

Calibrations are identified by git refs pointing at this plugin's source tree;
each ref's CLAUDE.md + invariants.txt + agents/*.md are concatenated as the
calibration content.

Probes are read from eval/questions/q*.md and eval/adversarial/adv*.md. Only
the `## Prompt` section of each probe file is sent to the model — `##
Expected shape`, `## Notable failure modes`, and `## Canary` are scoring /
contamination metadata that must not leak into the model's input.

`## Canary` (when present) holds a unique GUID per probe. The GUID is
extracted and written to the CSV column `canary_guid`; downstream
`scripts/check-canary-leak.py` greps responses for it — appearance of a
GUID in a response signals the model read the probe file (not just the
prompt) via the surrounding repo.

Prompt-caching mode (default):
    Calibration content is written once per (calibration) to a shared file
    (calib_path column). The probe-only user prompt is written per cell to
    prompt_path. ci_eval.py passes calibration as --system-prompt (cached by
    the API) and the probe as the user message, so all cells sharing the same
    calibration hit the cache after the first warm-up call.

    Legacy mode (--legacy-prompts): calibration + probe are concatenated into
    a single prompt_path file (old behaviour). This is NOT used by eval.yml —
    eval.yml calls run_suite.py without --legacy-prompts and validates the
    caching-mode output format, which is the production format. --legacy-prompts
    is a manual-compat flag only (e.g. for one-off debugging outside CI).

Usage:
    python3 run_suite.py \\
        --refs <sha-or-ref>=baseline,HEAD=candidate \\
        --probes questions,adversarial \\
        --k 5 \\
        --out results.csv \\
        --prompts-dir prompts/

CSV columns:
    probe_id, calibration, probe_kind, run_idx, prompt_path, calib_path,
    response_path, score_total, passed, canary_guid, criterion_scores

    calib_path — path to calibration file (system-prompt content); empty in
    legacy mode.

Score the responses against eval/criteria.md (binary 0/1), fill
response_path / score_total / passed (and optionally rater /
criterion_scores), then run statistical_test.py.
"""

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = SCRIPT_DIR.parent
REPO_ROOT = PLUGIN_DIR


def git_show(ref: str, plugin_relpath: str) -> str | None:
    target = f"{ref}:{plugin_relpath}"
    try:
        out = subprocess.run(
            ["git", "show", target],
            capture_output=True, text=True, check=True, cwd=REPO_ROOT,
        )
        return out.stdout
    except subprocess.CalledProcessError:
        return None


def calibration_content(ref: str) -> str:
    parts: list[str] = []
    for relpath, label in [
        ("CLAUDE.md", "CLAUDE.md"),
        ("invariants.txt", "invariants.txt"),
        ("agents/developer.md", "agents/developer.md"),
        ("agents/analyzer.md", "agents/analyzer.md"),
        ("agents/critic.md", "agents/critic.md"),
        ("agents/epistemic-auditor.md", "agents/epistemic-auditor.md"),
    ]:
        content = git_show(ref, relpath)
        if content:
            parts.append(f"### {label}\n\n{content.strip()}")
    return "\n\n---\n\n".join(parts)


def list_probes(kinds: list[str]) -> list[Path]:
    files: list[Path] = []
    if "questions" in kinds:
        files.extend(sorted((PLUGIN_DIR / "eval" / "questions").glob("q*.md")))
    if "adversarial" in kinds:
        files.extend(sorted((PLUGIN_DIR / "eval" / "adversarial").glob("adv*.md")))
    return files


_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def extract_section(text: str, name: str) -> str:
    """Return the body of `## <name>` up to the next `## ` heading or EOF.

    Empty string if the section is absent. Strips leading/trailing whitespace.
    """
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == name.lower():
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[start:end].strip()
    return ""


def extract_probe_prompt(text: str) -> str:
    body = extract_section(text, "Prompt")
    if not body:
        raise ValueError("probe file is missing `## Prompt` section")
    return body


def extract_canary(text: str) -> str:
    """Return the canary GUID from `## Canary`, or empty string if absent.

    Tolerates surrounding whitespace and inline comments — returns the first
    UUID-shaped token in the section body.
    """
    body = extract_section(text, "Canary")
    if not body:
        return ""
    m = re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        body,
    )
    return m.group(0) if m else body.split()[0]


def build_legacy_prompt(calibration: str, prompt_body: str) -> str:
    """Concatenated prompt used in legacy mode and eval.yml probe validation."""
    return (
        "Below is your operational protocol for this turn. Read it before "
        "answering. Then answer the prompt that follows, strictly applying "
        "the protocol.\n\n"
        "================ PROTOCOL ================\n\n"
        f"{calibration}\n\n"
        "================ PROMPT ================\n\n"
        f"{prompt_body}\n"
    )


def build_user_prompt(prompt_body: str) -> str:
    """User-side prompt for caching mode — probe only, no calibration prefix."""
    return (
        "Answer the following prompt, strictly applying the operational "
        "protocol in your system prompt.\n\n"
        "================ PROMPT ================\n\n"
        f"{prompt_body}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    ap.add_argument(
        "--refs", required=True,
        help="Comma-separated <ref>=<label> pairs",
    )
    ap.add_argument("--probes", default="questions,adversarial")
    ap.add_argument("--k", type=int, default=1, help="Runs per (probe × calibration). Default 1.")
    ap.add_argument("--out", default="results.csv")
    ap.add_argument("--prompts-dir", default="prompts")
    ap.add_argument(
        "--legacy-prompts", action="store_true",
        help=(
            "Write calibration + probe concatenated into prompt_path (old behaviour). "
            "calib_path column will be empty. Used by eval.yml probe-validation step."
        ),
    )
    args = ap.parse_args()

    if args.k < 1:
        print("--k must be >= 1", file=sys.stderr)
        return 2

    refs = [pair.split("=", 1) for pair in args.refs.split(",")]
    probe_kinds = [k.strip() for k in args.probes.split(",") if k.strip()]
    probes = list_probes(probe_kinds)
    if not probes:
        print(f"No probes found for kinds {probe_kinds}", file=sys.stderr)
        return 2

    prompts_root = Path(args.prompts_dir)
    prompts_root.mkdir(parents=True, exist_ok=True)

    csv_rows: list[dict[str, str]] = []
    for ref, label in refs:
        calib = calibration_content(ref)
        if not calib:
            print(
                f"Calibration at ref {ref} ({label}) empty — skipping",
                file=sys.stderr,
            )
            continue
        out_dir = prompts_root / label
        out_dir.mkdir(parents=True, exist_ok=True)

        # Write calibration file once per calibration label (caching mode).
        calib_path_str = ""
        if not args.legacy_prompts:
            calib_file = out_dir / "_calibration.txt"
            calib_file.write_text(calib, encoding="utf-8")
            calib_path_str = str(calib_file)

        for probe_path in probes:
            pid = probe_path.stem
            text = probe_path.read_text(encoding="utf-8")
            prompt_body = extract_probe_prompt(text)
            canary = extract_canary(text)

            for run in range(args.k):
                fname = f"{pid}.txt" if args.k == 1 else f"{pid}_r{run}.txt"
                if args.legacy_prompts:
                    prompt = build_legacy_prompt(calib, prompt_body)
                    (out_dir / fname).write_text(prompt, encoding="utf-8")
                else:
                    user_prompt = build_user_prompt(prompt_body)
                    (out_dir / fname).write_text(user_prompt, encoding="utf-8")

                csv_rows.append({
                    "probe_id": pid,
                    "calibration": label,
                    "probe_kind": "adv" if pid.startswith("adv") else "q",
                    "run_idx": str(run),
                    "prompt_path": str(out_dir / fname),
                    "calib_path": calib_path_str,
                    "response_path": "",
                    "score_total": "",
                    "passed": "",
                    "canary_guid": canary,
                    "criterion_scores": "",
                })

    cols = [
        "probe_id", "calibration", "probe_kind", "run_idx",
        "prompt_path", "calib_path", "response_path",
        "score_total", "passed", "canary_guid", "criterion_scores",
    ]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(csv_rows)

    mode = "legacy" if args.legacy_prompts else "caching"
    print(
        f"Wrote {len(csv_rows)} prompts under {prompts_root}/ "
        f"and stub results to {args.out} [{mode} mode]."
    )
    if not args.legacy_prompts:
        print(
            "Calibration system prompts written to <label>/_calibration.txt — "
            "pass calib_path as --system-prompt to claude for cache reuse."
        )
    else:
        print(
            "Next: send each prompt to Claude (API / CLI / sub-agent), capture "
            "response, score against eval/criteria.md, fill response_path / "
            "score_total / passed. Then run scripts/check-canary-leak.py and "
            "statistical_test.py."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
