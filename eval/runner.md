# How to run the suite

Manual workflow — score the reply, feed `results.csv` to `statistical_test.py`.

## One question, one calibration

1. Open a fresh Claude session with this plugin enabled.
2. (Optional) If testing a *candidate* calibration, point Claude at the candidate `CLAUDE.md` / `invariants.txt` / agents instead of the merged ones.
3. Paste the question's prompt from `questions/qNN.md` verbatim. No extra context, no follow-up turns — single-turn measurement.
4. Save the reply.
5. Score against `criteria.md` using the `## Expected shape` block as the anchor.

## Full suite

Repeat the above for every `questions/qNN.md` and `adversarial/advNN.md`. For higher reliability, run k=3–5 times per (probe × calibration) — `run_suite.py --k 5` writes one prompt file per run; `statistical_test.py` median-aggregates per cell before pairing.

Per-criterion 0/1 scores can be recorded in the `criterion_scores` column (comma-separated 17 digits) — enables Krippendorff α when ≥2 raters score the same (probe × calibration).

## A/B-comparing two calibrations

1. Run the full suite against calibration A and B.
2. Run `scripts/check-canary-leak.py results.csv` — any leak fails the eval (the model read the probe file via repo grep, not just the prompt).
3. Feed `results.csv` to `statistical_test.py --baseline A --candidate B`.
4. Decision rule (pre-registered): Wilcoxon p < 0.05 on q-totals, Cohen's d 95% bootstrap CI lower bound > 0.2, zero McNemar regressions on adversarial (regression = probe pass_fraction drops by > 0.5 between calibrations, making noise-only 2/3→1/3 flips at k=3 non-counting), zero canary leaks.

## What to do with a regression

A regression on any single question while making a CLAUDE.md change means: the change is fighting an invariant that was previously satisfied. Either:
- The invariant the question was probing has changed deliberately (acknowledge in the MR, update the question's *Expected shape*).
- Or the change has an unintended side-effect (revert or refine).
