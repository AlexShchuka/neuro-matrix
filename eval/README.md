# Held-out eval suite

A repeatable measurement of the protocol's effect on agent behaviour. Without this suite every change to `CLAUDE.md`, `invariants.txt`, or sub-agent prompts is a taste call — there is no way to tell whether a tweak made the system better, worse, or just different.

## What's in here

- `criteria.md` — the 17-criteria binary rubric, with scoring rules.
- `questions/` — holds 6 session-derived probes (q01–q06); add more per `questions/README.md`.
- `adversarial/` — adversarial probes designed to trip invariants under deliberate bypass attempts.
- `runner.md` — manual workflow for grading a calibration against the suite.
- `run_suite.py` + `statistical_test.py` — Layer E harness (k-run aggregation, paired Wilcoxon, bootstrap CI on Cohen's d, McNemar one-sided, Krippendorff α).

## When to re-run

- After any change to `CLAUDE.md`, `invariants.txt`, agent prompts, or hook scripts in this plugin.
- On a fixed schedule (e.g. every 2 weeks) to catch regressions from upstream model changes.
- Before merging a change that touches the protocol — minimum threshold for merge is **no question regresses below its current score**.

## What "golden response shape" means

Not a single canonical text. A *shape* — the structural properties the reply must satisfy: e.g. *«surfaces 2–3 variants»*, *«marks associative inference inline»*, *«does not invent the term `хербит`»*. Two replies with different wording can both satisfy the shape.

Shapes live inside each question file under the `## Expected shape` section.

## Sources

- Real developer questions encountered while using the plugin. Add new probes under `questions/qNN.md` following the format from `adversarial/` (one file per probe: `# qNN — short title` + `## Prompt` + `## Expected shape`).

## Validity caveats

- Same underlying model on both sides → some convergence is from the shared prior, not the protocol. External judge (different family) or multi-judge aggregation lifts this — see `ROADMAP.md`.
- 17 binary criteria are coarse — they catch shape, not subtle quality. Treat scores as a regression alarm, not as a quality ceiling.
- The suite is small (17: 11 adversarial + 6 questions). Use `statistical_test.py` (paired Wilcoxon + bootstrap CI on Cohen's d) to separate signal from noise.
