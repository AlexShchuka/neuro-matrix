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
| N3 | role-invariants index off-by-one | `scripts/role-invariants.sh:31` — `sed` reads file lines, but line 1 of `invariants.txt` is the header comment, so invariant #N sits on file line N+1 | Sub-agents inherit the wrong invariant lines under `<inherited-invariants>`. | open |
| N4 | Not installable via marketplace | repo root — no `.claude-plugin/marketplace.json` | Plugin cannot be added with `/plugin`; only manual / local load. | open |
| N5 | Anchor freshness debt | `references/research-anchors.md` — most rows `pending-verification`, `Last-verified: —` | The quarterly-review cadence is defined but has not run; R24 is the automation candidate. | open |

(N4 — marketplace manifest — shipped as S2 below.)

## Shipped

| # | Item | Anchor | Landed |
|---|---|---|---|
| S1 | Verification gate — the verification half of an EviBound-style dual gate, complementing the approval gate (`auto-critic.sh`) | `scripts/verification-gate.sh`; vector R33 | PR #1 (open) |
| S2 | Discoverability enablers — installable + directory-listable marketplace manifest, README/landing SEO+GEO, `llms.txt`, Apache-2.0 license | `.claude-plugin/marketplace.json`, `docs/index.html`, `llms.txt`, `LICENSE` | this PR |

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
