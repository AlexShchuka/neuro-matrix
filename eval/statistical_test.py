#!/usr/bin/env python3
"""
Statistical test for plugin Layer E pre-registered decision rule.

Reads results.csv (produced by run_suite.py and then scored) with columns:
    probe_id, calibration, probe_kind, prompt_path, response_path,
    score_total, passed
    [run_idx]          — optional, default "0"; k>1 runs aggregated as median
                         per (probe_id, calibration) before pairing.
    [rater]            — optional, default "1"; enables Krippendorff α when
                         ≥2 raters score the same (probe_id, calibration) and
                         criterion_scores is present.
    [criterion_scores] — optional, CSV-string of 17 binary digits per row;
                         e.g. "1,0,1,1,0,1,...,1". Skipped if absent.
    [canary_guid]      — optional, anti-contamination marker checked by
                         scripts/check-canary-leak.py.

Pre-registered decision rule (unchanged):
    - Paired Wilcoxon signed-rank on q-probe `score_total`
      (paired by probe_id across baseline vs candidate calibration).
    - McNemar one-sided on adv-probe `pass_fraction` (noise-robust):
      a regression is counted only when pass_fraction drops by > 0.5
      between baseline and candidate (i.e. a clear majority flip from
      pass to fail, not a single-run noise flip at k=3).
    - Bootstrap 95% CI on Cohen's d of per-question deltas.

Verdict: candidate MR mergeable iff ALL:
    Wilcoxon p < 0.05 AND
    Cohen's d 95% bootstrap CI lower bound > 0.2 AND
    no significant adversarial regression (McNemar one-sided p < 0.05).

Wilcoxon uses scipy if available; otherwise falls back to NaN. McNemar,
bootstrap CI, and Krippendorff α are stdlib-only.

Usage:
    python3 statistical_test.py results.csv --baseline <prev-label> --candidate <new-label>
"""

import argparse
import csv
import math
import random
import statistics
import sys
from collections import defaultdict
from typing import Optional


Key = tuple[str, str]  # (probe_id, calibration)


def load_results(path: str) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def aggregate_runs(
    rows: list[dict[str, str]],
) -> dict[Key, dict[str, float | str]]:
    """Median-aggregate score_total per (probe_id, calibration) across runs and raters.

    `passed` collapses by majority (>= 0.5 fraction). probe_kind is carried
    from the first row of the group.
    """
    grouped: dict[Key, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key: Key = (row["probe_id"], row["calibration"])
        grouped[key].append(row)

    out: dict[Key, dict[str, float | str]] = {}
    for key, group in grouped.items():
        scores: list[float] = []
        passes: list[float] = []
        for r in group:
            try:
                scores.append(float(r.get("score_total", "")))
            except ValueError:
                pass
            passes.append(
                1.0 if r.get("passed", "").strip().lower() in {
                    "1", "true", "pass", "yes"
                } else 0.0
            )
        pass_frac = (sum(passes) / len(passes)) if passes else 0.0
        out[key] = {
            "probe_kind": group[0].get("probe_kind", ""),
            "score_total": statistics.median(scores) if scores else float("nan"),
            "passed": 1.0 if pass_frac >= 0.5 else 0.0,
            # pass_fraction: raw fraction for noise-robust McNemar (see mcnemar_one_sided).
            "pass_fraction": pass_frac,
        }
    return out


def collect_pairs(
    agg: dict[Key, dict[str, float | str]],
    baseline: str,
    candidate: str,
    kind: str,
) -> tuple[list[float], list[float]]:
    probe_ids = sorted({pid for (pid, c) in agg if c == baseline})
    b_out: list[float] = []
    c_out: list[float] = []
    for pid in probe_ids:
        b = agg.get((pid, baseline))
        c = agg.get((pid, candidate))
        if not b or not c or b.get("probe_kind") != kind:
            continue
        # adv probes use pass_fraction for noise-robust McNemar; q-probes use score_total.
        col = "pass_fraction" if kind == "adv" else "score_total"
        try:
            b_val = float(b[col])
            c_val = float(c[col])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isnan(b_val) or math.isnan(c_val):
            continue
        b_out.append(b_val)
        c_out.append(c_val)
    return b_out, c_out


def cohens_d_paired(b: list[float], c: list[float]) -> float:
    diffs = [ci - bi for bi, ci in zip(b, c)]
    if len(diffs) < 2:
        return 0.0
    sd = statistics.stdev(diffs)
    if sd == 0:
        return 0.0
    return statistics.mean(diffs) / sd


def bootstrap_ci(
    b: list[float],
    c: list[float],
    n_samples: int = 5000,
    ci_level: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    diffs = [ci - bi for bi, ci in zip(b, c)]
    if len(diffs) < 2:
        return (0.0, 0.0)
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(n_samples):
        sample = [rng.choice(diffs) for _ in diffs]
        try:
            sd = statistics.stdev(sample)
        except statistics.StatisticsError:
            sd = 0.0
        samples.append(statistics.mean(sample) / sd if sd else 0.0)
    samples.sort()
    lo_i = int((1 - ci_level) / 2 * n_samples)
    hi_i = int((1 + ci_level) / 2 * n_samples) - 1
    return (samples[lo_i], samples[hi_i])


def wilcoxon_p(b: list[float], c: list[float]) -> Optional[float]:
    try:
        from scipy.stats import wilcoxon  # type: ignore
    except ImportError:
        return None
    diffs = [ci - bi for bi, ci in zip(b, c)]
    if not any(d != 0 for d in diffs):
        return 1.0
    res = wilcoxon(diffs)
    return float(res.pvalue)


def mcnemar_one_sided(b: list[float], c: list[float]) -> tuple[int, int, float]:
    """Noise-robust McNemar on pass_fraction values (not binary passed).

    A regression is counted only when the candidate pass_fraction drops by more
    than 0.5 relative to baseline — i.e. the probe went from majority-pass
    (frac > 0.5) to majority-fail (frac <= 0.5) by a CLEAR margin, not a
    single-run noise flip. With k=3, fractions are {0, 1/3, 2/3, 1}; a
    2/3 → 1/3 noise flip (diff=1/3) is excluded; only 1 → 1/3 (diff=2/3)
    or cleaner drops count.

    This fixes the null-comparison artifact (live run 2026-06-11: 4 regressions
    on identical calibrations at k=3) without masking genuine regressions where
    the probe clearly fails in the candidate.
    """
    regressions = sum(1 for bi, ci in zip(b, c) if bi - ci > 0.5)
    improvements = sum(1 for bi, ci in zip(b, c) if ci - bi > 0.5)
    n = regressions + improvements
    if n == 0:
        return (0, 0, 1.0)
    p = sum(math.comb(n, k) for k in range(regressions + 1)) / (2 ** n)
    return (regressions, improvements, p)


def parse_criterion_scores(s: str) -> list[Optional[int]]:
    """Parse a CSV string of 17 per-criterion scores.

    Accepts `0`, `1`, or `n/a` (`na`) per criterion — `n/a` means the
    criterion did not apply to this probe and the position is skipped by
    `alpha_per_calibration`. Returns [] (and the row is dropped) only if a
    token is genuinely malformed.
    """
    out: list[Optional[int]] = []
    for piece in s.split(","):
        piece = piece.strip().lower()
        if piece == "":
            continue
        if piece in ("n/a", "na"):
            out.append(None)
            continue
        try:
            v = int(piece)
        except ValueError:
            return []
        if v not in (0, 1):
            return []
        out.append(v)
    return out


def krippendorff_alpha_binary(
    ratings_by_unit: list[list[int]],
) -> Optional[float]:
    """Krippendorff α for binary nominal data.

    ratings_by_unit[u] = list of binary ratings from raters who scored unit u
    (n/a positions are filtered upstream). Units with <2 raters contribute
    zero pairs. Returns None when fewer than one pairable unit exists.
    """
    pairs_within: float = 0.0
    pairs_total: float = 0.0
    counts = [0, 0]

    for ratings in ratings_by_unit:
        m = len(ratings)
        if m < 2:
            continue
        zeros = sum(1 for r in ratings if r == 0)
        ones = m - zeros
        pairs_within += 2 * zeros * ones / (m - 1)
        pairs_total += m
        counts[0] += zeros
        counts[1] += ones

    if pairs_total < 2 or counts[0] + counts[1] < 2:
        return None
    n = counts[0] + counts[1]
    expected = 2.0 * counts[0] * counts[1] / (n * (n - 1))
    observed = pairs_within / pairs_total
    if expected == 0:
        return 1.0 if observed == 0 else None
    return 1.0 - observed / expected


def alpha_per_calibration(
    rows: list[dict[str, str]],
) -> dict[str, Optional[float]]:
    """Compute α per calibration, aggregating units across probes.

    Each (probe_id × criterion_index) is one unit; raters provide 0/1 for
    each (n/a positions are skipped — they did not apply to that probe).
    """
    if not any("criterion_scores" in r and r.get("criterion_scores") for r in rows):
        return {}
    by_calib_unit: dict[str, dict[tuple[str, int], list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for r in rows:
        cs = r.get("criterion_scores", "")
        if not cs:
            continue
        scores = parse_criterion_scores(cs)
        if not scores:
            continue
        calib = r["calibration"]
        pid = r["probe_id"]
        for i, v in enumerate(scores):
            if v is None:
                continue
            by_calib_unit[calib][(pid, i)].append(v)

    out: dict[str, Optional[float]] = {}
    for calib, units in by_calib_unit.items():
        ratings = list(units.values())
        out[calib] = krippendorff_alpha_binary(ratings)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    ap.add_argument("results_csv")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    args = ap.parse_args()

    rows = load_results(args.results_csv)
    agg = aggregate_runs(rows)
    q_b, q_c = collect_pairs(agg, args.baseline, args.candidate, "q")
    a_b, a_c = collect_pairs(agg, args.baseline, args.candidate, "adv")

    print(
        f"Pairs: q={len(q_b)}, adv={len(a_b)} "
        f"({args.baseline} → {args.candidate})"
    )

    p = wilcoxon_p(q_b, q_c) if q_b else None
    d = cohens_d_paired(q_b, q_c) if q_b else 0.0
    ci_lo, ci_hi = bootstrap_ci(q_b, q_c) if q_b else (0.0, 0.0)
    regs, imps, mp = (
        mcnemar_one_sided(a_b, a_c) if a_b else (0, 0, 1.0)
    )

    p_str = f"{p:.4f}" if p is not None else "n/a (scipy missing)"
    print(f"Wilcoxon p (q-totals):  {p_str}")
    print(
        f"Cohen's d (paired):     {d:.3f}  "
        f"[95% bootstrap CI: {ci_lo:.3f}, {ci_hi:.3f}]"
    )
    print(
        f"McNemar adv:            {regs} regressions, "
        f"{imps} improvements, p(one-sided)={mp:.4f}"
    )

    alphas = alpha_per_calibration(rows)
    for calib in (args.baseline, args.candidate):
        a = alphas.get(calib)
        if a is None:
            continue
        print(f"Krippendorff α [{calib}]: {a:.3f} (target ≥ 0.8)")

    failing: list[str] = []
    if p is None:
        failing.append("Wilcoxon=n/a (install scipy to run the real test)")
    elif p >= 0.05:
        failing.append(f"Wilcoxon p {p:.3f} ≥ 0.05")
    if ci_lo <= 0.2:
        failing.append(f"Cohen's d CI lower {ci_lo:.3f} ≤ 0.2")
    if mp < 0.05:
        failing.append(f"McNemar p={mp:.4f} < 0.05 (significant adversarial regression)")

    if not failing:
        print("\nVERDICT: APPROVE — all pre-registered conditions met.")
        return 0
    print("\nVERDICT: FIX-REQUIRED — failing conditions:")
    for v in failing:
        print(f"  - {v}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
