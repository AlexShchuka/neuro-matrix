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
| N1 | Stack scaffolds absent | `references/per-stack/` — referenced by `CLAUDE.md:68`, `agents/developer.md:39`, `agents/analyzer.md:44`; only a `README.md` ships | Agents are instructed to read per-stack rules before acting; without `<stack>.md` files the instruction has no target. | open |
| N2 | No positive eval probes | `eval/questions/` holds only `README.md`; `eval/run_suite.py:87` globs `q*.md` → empty | The statistical harness (Wilcoxon / McNemar) has no positive set to run on; only adversarial probes exist. | open |
| N3 | role-invariants index off-by-one | `scripts/role-invariants.sh` — `sed` read file lines, but line 1 of `invariants.txt` is the header comment, so invariant #N sat on file line N+1 | Sub-agents inherited the wrong invariant lines under `<inherited-invariants>`. | open |
| N4 | Not installable via marketplace | repo root — no `.claude-plugin/marketplace.json` | Plugin cannot be added with `/plugin`; only manual / local load. | open |
| N5 | Anchor freshness debt | `references/research-anchors.md` — most rows `pending-verification`, `Last-verified: —` | The quarterly-review cadence is defined but has not run; R24 is the automation candidate. | open |
| N6 | Hard-prohibitions have no deterministic guard | `hooks/hooks.json`, `scripts/` — no `PreToolUse` hook blocks `git push` to main / `--force` / `--no-verify`; `invariants.txt #24` is advisory/sampler-only (not yet inherited by any role — see N8) | An irreversible shared-history action is guarded only by a low-probability weighted self-check and prose, not a deterministic gate. Add a `PreToolUse` red-line guard as the durable backstop. | open |
| N7 | Verification gate covers only `sh`/`py`/`json` | `scripts/verification-gate.sh` (case block) | On compiled/typed stacks (C#, TS/TSX, Swift) the verification half of the dual gate no-ops, silently degrading to approval-only on the languages most projects ship — the regime EviBound measures at ≈25–100% false-completion. Add stack-aware checks (`tsc --noEmit`, `dotnet build`/`format --verify-no-changes`, `swift build`). | open |
| N8 | Role subsets omit #23/#24/#25; analyzer not least-privilege | `scripts/role-invariants.sh` (subsets); `agents/analyzer.md`, `agents/developer.md` (no `tools:` field → inherit all tools) | The verification-gate (#23) and the new red-line (#24) / halt-on-contradiction (#25) invariants are inherited by no role; analyzer is documented non-mutating yet can `Edit`/`Write`/`Bash`. Curate the subsets and scope tools — calibration change, gate behind the eval suite. | open |

(N3 — role-invariants off-by-one — shipped as S3 below.)
(N4 — marketplace manifest — shipped as S2 below.)

## Shipped

| # | Item | Anchor | Landed |
|---|---|---|---|
| S1 | Verification gate — the verification half of an EviBound-style dual gate, complementing the approval gate (`auto-critic.sh`) | `scripts/verification-gate.sh`; vector R33 | PR #1 (open) |
| S2 | Discoverability enablers — installable + directory-listable marketplace manifest, README/landing SEO+GEO, `llms.txt`, PolyForm Noncommercial 1.0.0 license | `.claude-plugin/marketplace.json`, `docs/index.html`, `llms.txt`, `LICENSE` | this PR |
| S3 | Invariant-set integrity & coverage — stable `#N` ids addressed by `grep` (not file line), fixed role-inheritance off-by-one (N3) + stale cross-refs, deontic/Counter consistency (#15/#19/#23), and two new invariants (#24 hard-prohibitions, #25 halt-on-contradiction) | `invariants.txt`, `scripts/role-invariants.sh`, `scripts/random-invariant.sh`, `CLAUDE.md`, `agents/epistemic-auditor.md` | this PR (`alexshchuka/invariant-integrity-and-gaps`) |

## Discoverability — maintainer actions (not automatable in a PR)

A PR ships repo files; the acts below are GitHub settings or external submissions only the maintainer can perform. Together with S2 they answer "why nobody sees it yet."

- [ ] Set repo **About** (problem-focused one-liner) + up to 20 **topics**: `claude-code` `claude-code-plugin` `claude-code-marketplace` `ai-agents` `llm` `agentic-ai` `prompt-engineering` `hooks` `subagents` `ai-code-review` `anti-hallucination` `llm-evaluation` `developer-tools` `ai-safety` `constitutional-ai` `systems-thinking`.
- [ ] Enable **GitHub Pages** (source: `/docs`) → landing indexed by search + AI engines; then point `homepage` in `marketplace.json` at the Pages URL.
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
