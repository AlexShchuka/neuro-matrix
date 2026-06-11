# eval/acceptance-d — Artifact Acceptance Kit (issue #30)

Pre-declared acceptance checks for D's artifacts. When D publishes his code, run
this kit immediately to verify the deliverables meet the criteria agreed in issue #30.

---

## Directory contents

| File | What it is |
|---|---|
| `selftest.py` | Combined selftest + acceptance runner (stdlib only, no network) |
| `fixtures/comment-3.txt` | FAIL fixture: comment id=4673640305 verbatim (deference tone — expected to be rejected by `issue_answer_check.py`) |
| `fixtures/comment-9.txt` | PASS fixture: comment id=4679555540 verbatim (peer tone — expected to be accepted) |
| `fixtures/good.jsonl` | Good common-code sample (copy of `common-code.sample.jsonl`); expected exit 0 |
| `fixtures/bad1.jsonl` | FAIL RETRIEVAL: one FACT record with empty `source` field |
| `fixtures/bad2.jsonl` | FAIL JSON: truncated/invalid JSON line |
| `fixtures/bad3.jsonl` | FAIL SHAPE: verdict `"MAYBE"` (not in `{MATCH, DIVERGE}`) |
| `fixtures/big.jsonl` | FAIL BUDGET: 31 rows (exceeds N_inv cap of 30) |
| `checklist-ru.md` | Human-facing Russian checklist for D: how to publish code without secrets |

---

## Running selftest mode

Selftest verifies **our symmetric exchange**: the common-code validator correctly
rejects each bad fixture with exactly its one expected error code, and passes the
good sample.

```bash
# Default: expects validator at scripts/check_common_code.py (issue #29 branch)
python3 eval/acceptance-d/selftest.py

# Override validator path (e.g. before issue #29 merges):
python3 eval/acceptance-d/selftest.py --validator /workspace/check_common_code.py
```

Expected output: five `PASS` lines and `selftest: ALL PASS`.

---

## Running acceptance mode

Once D has published his repo, clone it and run:

```bash
python3 eval/acceptance-d/selftest.py \
    --acceptance /path/to/d-repo \
    --validator scripts/check_common_code.py
```

The runner attempts all four checks declared in issue #30:

| Check | D's artifact | What is verified |
|---|---|---|
| 1 | `issue_answer_check.py` | comment-3 fixture → nonzero exit (FAIL); comment-9 fixture → exit 0 (PASS) |
| 2 | `drift_guard.py` | commit without `go:user` tag → nonzero; ledger machine-readable, ≥10 entries with source tag, ≥1 tagged `мой-дрейф` |
| 3 | `frontier.py` | 1 quality point + 0 cost points → `INSUFFICIENT_POINTS` in output, no curve file generated |
| 4 | `[A]/[B]/[C]` classification artifact | artifact exists; ≥1 deterministic class-A test reproducible by us (exit 0) |

Checks print `SKIP <reason>` for any artifact not yet present in D's repo.
The runner exits 0 only if all runnable checks pass.

---

## Awaiting D's code

The following artifacts are not yet available and will be SKIPped until D publishes:

- `issue_answer_check.py` — tone gate
- `drift_guard.py` — drift ledger pre-commit
- `frontier.py` — quality/cost frontier
- `[A]/[B]/[C]` classification artifact (name TBD)

---

## Validator location note

`selftest.py` defaults to `scripts/check_common_code.py` (delivered by the issue-#29
parallel branch). If that branch has not merged yet, pass `--validator <path>` to
point at the working copy. The validator itself is **not** committed on this branch
to avoid merge conflicts with issue #29.
