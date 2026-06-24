# ROADMAP — neuro-matrix

Canonical home for every planned improvement. **Self-contained: nothing here points outside this repository.** `references/research-anchors.md` is the source catalog that feeds this file by ID — its `Used in` column resolves to the layers and vectors below.

Status legend: `open` (planned) · `in-progress` · `shipped` · `reserved` (awaiting maintainer input).

## How to use this file

- New improvement → add a row here first. This is the backlog of record.
- Needs a citation → add the source to `references/research-anchors.md`, then reference it by ID from the row here.
- Item ships → move it to **Shipped** with the landing PR.

## Near-term (verified, actionable)

Each item is anchored to a concrete repo location, confirmed by tool output.

| # | Item | Anchor | Why it matters | Status |
|---|---|---|---|---|
| N1 | Stack scaffolds partial | `references/per-stack/` — referenced by `CLAUDE.md:68`, `agents/developer.md:39`, `agents/analyzer.md:44`; `python.md` shipped (#70), but `ts`/`cs`/`swift`/`go` are still absent | Agents are instructed to read per-stack rules before acting; python now has a target, but the other stacks still have none. | in-progress |
| N2 | No positive eval probes | `eval/questions/` holds only `README.md`; `eval/run_suite.py:87` globs `q*.md` → empty | The statistical harness (Wilcoxon / McNemar) has no positive set to run on; only adversarial probes exist. | open |
| N4 | Not installable via marketplace | repo root — no `.claude-plugin/marketplace.json` | Plugin cannot be added with `/plugin`; only manual / local load. | open |
| N5 | Anchor freshness debt | `references/research-anchors.md` — most rows `pending-verification`, `Last-verified: —` | The quarterly-review cadence is defined but has not run; R24 is the automation candidate. | open |
| N6 | Hard-prohibitions have no deterministic guard | `hooks/hooks.json`, `scripts/` — no `PreToolUse` hook blocks `git push` to main / `--force` / `--no-verify`; `invariants.txt #24` is advisory/sampler-only (not yet inherited by any role — see N8) | An irreversible shared-history action is guarded only by a low-probability weighted self-check and prose, not a deterministic gate. Add a `PreToolUse` red-line guard as the durable backstop. | shipped |
| N7 | Verification gate covers only `sh`/`py`/`json` | `scripts/verification-gate.sh` (case block) | On compiled/typed stacks (C#, TS/TSX, Swift) the verification half of the dual gate no-ops, silently degrading to approval-only on the languages most projects ship — the regime EviBound measures at ≈25–100% false-completion. Add stack-aware checks (`tsc --noEmit`, `dotnet build`/`format --verify-no-changes`, `swift build`). | shipped |
| N8 | Role subsets omit #23/#24/#25 | `scripts/role-invariants.sh` (subsets) | The verification-gate (#23) and the new red-line (#24) / halt-on-contradiction (#25) invariants are inherited by no role. Curate the subsets — calibration change, gate behind the eval suite. | open |
| N9 | Dispatch guidance omits skills | `CLAUDE.md` "Request routing" — role-agent table only, grep returns no skill mention; the 5 enabled skills (`adversarial-review`, `agent-fleet-orchestration`, `robust-by-construction`, `harness-improve`, `paper-to-code`) are never routed to | The routing table trained the model to reach for `subagent_type` and never the skills — reproduced in a long mirabilis session where adversarial review + fleet orchestration were hand-built from scratch instead of invoked. Added a Skill-routing block with a Counter. | shipped |
| N10 | Skill-consult check before agent spawn | `hooks/` — a `PreToolUse` reminder (`scripts/skill-consult-check.sh`, wired in `hooks/hooks.json` on the `Agent` matcher) now fires a skill-match check before an `Agent` spawn whose description matches a skill trigger | Mechanical backstop for N9: text guidance erodes under load (same class as N6); a deterministic pre-spawn nudge catches the miss N9 documents. | shipped |

(N2 — positive eval probes — shipped as S5 below.)
(N3 — role-invariants off-by-one — shipped as S3 below.)
(N4 — marketplace manifest — shipped as S2 below.)

## Shipped

| # | Item | Anchor | Landed |
|---|---|---|---|
| S1 | Verification gate — the verification half of an EviBound-style dual gate, complementing the approval gate (`auto-critic.sh`) | `scripts/verification-gate.sh`; vector R33 | PR #1 (merged) |
| S2 | Discoverability enablers — installable + directory-listable marketplace manifest, README/landing SEO+GEO, `llms.txt`, MIT License | `.claude-plugin/marketplace.json`, `docs/index.html`, `llms.txt`, `LICENSE` | this PR |
| S3 | Invariant-set integrity & coverage — stable `#N` ids addressed by `grep` (not file line), fixed role-inheritance off-by-one (N3) + stale cross-refs, deontic/Counter consistency (#15/#19/#23), and two new invariants (#24 hard-prohibitions, #25 halt-on-contradiction) | `invariants.txt`, `scripts/role-invariants.sh`, `scripts/random-invariant.sh`, `CLAUDE.md`, `agents/epistemic-auditor.md` | this PR (`alexshchuka/invariant-integrity-and-gaps`) |
| S4 | Repo hygiene cleanup — `.gitignore` added; `eval/README.md` inaccuracies fixed (questions bullet, probe count, broken ref); `docs/DISCOVERABILITY.md` stale merge-order removed + canonical pointer to `ROADMAP.md`; orphan scripts (`notion-page-dump.py`, `tracker-context.py`) removed; `verification-gate.sh` ported to bash-3.2 (`mapfile`/`declare -A` replaced); `agents/analyzer.md` scoped to least-privilege `tools: Read, Grep, Glob` (N8 partial) | `.gitignore`, `eval/README.md`, `docs/DISCOVERABILITY.md`, `scripts/verification-gate.sh`, `agents/analyzer.md`, `ROADMAP.md` | PR `alexshchuka/repo-review-cleanup` |
| S5 | Positive eval probes (N2) — q01–q06 authored from real sessions; `run_suite.py` glob no longer empty | `eval/questions/q01.md`–`q06.md` | PR #34 |
| S6 | Skill-consult PreToolUse check (N10) — deterministic pre-spawn nudge fires a skill-match check before an `Agent` spawn whose description matches a skill trigger; mechanical backstop for N9 | `scripts/skill-consult-check.sh`, `hooks/hooks.json` (Agent matcher) | PR #71 |
| S7 | Deterministic redline guard (N6) — PreToolUse hook on Bash that mechanically blocks force-push, --no-verify, local merge/rebase onto main, PR/MR merge/close/delete, and production k8s/helm mutations; exits 2 on positive match, 0 otherwise; wired as the first Bash hook (before verification-gate and auto-critic) | `scripts/redline-guard.sh`, `scripts/selftest_redline-guard.sh`, `hooks/hooks.json` | branch `harness/door-2-mainpush-delegation` |

## Discoverability — maintainer actions (not automatable in a PR)

A PR ships repo files; the acts below are GitHub settings or external submissions only the maintainer can perform. Together with S2 they answer "why nobody sees it yet."

- [ ] Set repo **About** (problem-focused one-liner) + up to 20 **topics**: `claude-code` `claude-code-plugin` `claude-code-marketplace` `ai-agents` `llm` `agentic-ai` `prompt-engineering` `hooks` `subagents` `ai-code-review` `anti-hallucination` `llm-evaluation` `developer-tools` `ai-safety` `constitutional-ai` `systems-thinking`.
- [ ] Submit to the **Anthropic official directory** (`anthropics/claude-plugins-official`) via their submission form — expect a quality/security review (coordinate with issue #4 on what is exposed).
- [ ] Open PRs into the live awesome-lists: `hesreallyhim/awesome-claude-code` (canonical), `ComposioHQ/awesome-claude-plugins`, `Chat2AnyLLM/awesome-claude-plugins`.
- [ ] Check whether **claudemarketplaces.com** lists the repo (reportedly updated daily from GitHub; not independently verified).
- [ ] Publish the Habr article (issue #3) + cross-post for backlinks (the strongest ranking signal for a new repo).

## Strategic layer (reserved — awaiting the maintainer's roadmap document)

The layered design (L1–L10, meta-axioms, R-vectors) is tracked by ID in `references/research-anchors.md` and will be imported here from the maintainer's roadmap document. Until then, this section is the in-repo target those IDs resolve to — so the catalog references stay internal and consistent.

Layers currently referenced by the catalog, with the theme stated in its section headers:

- **L1, L6** — game theory + mechanism design
- **L2, L5** — systems / CAS / phase transition
- **L3** — deontic + constrained MDP
- **L4, L7** — ODE / control theory
- **L8** — chaos / dynamical systems
- **L9** — variance decomposition
- **L10** — cultural transmission / cognitive
- **meta-axiom 4** — externalization + cognitive scaffolding

Vectors referenced by the catalog, descriptions pending import: R5, R6, R9, R15, R16, R22, R24, R30, R31, R33 (→ shipped, S1), R34, R35.
