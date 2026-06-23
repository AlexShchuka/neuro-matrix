# neuro-matrix

A Claude Code plugin that calibrates an AI + developer co-system on common sense, scientific method, and Nash-equilibrium cooperation. Agents, hooks, an invariant-driven self-check, and a held-out evaluation harness.

**What it is:** an anti-hallucination («anti-neuroslop») **harness for Claude Code** — runtime **invariants** with a per-turn self-check, deterministic **hooks**, five **agents** (developer · analyzer · critic · epistemic-auditor · translator), a dual approval+verification gate, and a held-out **evaluation harness** that keep AI-assisted coding anchored to reality. *Topics: Claude Code plugin, AI agents, prompt engineering, LLM evaluation, AI code review, hooks, agentic, AI safety.*

## Install

```text
/plugin marketplace add AlexShchuka/neuro-matrix
/plugin install neuro-matrix@neuro-matrix
```

Requires [Claude Code](https://code.claude.com). On install: a risk-weighted invariant self-check each turn, cycle / critic / verification hooks on mutations, five sub-agents for analysis, code, review, epistemic audit, and codebook translation.

The operating protocol lives in `CLAUDE.md`. This README answers: **why, on what concepts, how to work as a team, and what the project is for.**

The name is a nod to John Forbes Nash Jr. — payoff matrices in game theory, the mind matrices Nash drew on glass in *A Beautiful Mind*, and the neurodivergent cognitive style that powers systems thinking under uncertainty.

## 1. Goals

**Defensive**: keep AI-scaled development from degrading the codebase and engineering culture.

What the industry shows:
- Duplicated code blocks growing multi-fold (GitClear «AI Copilot Code Quality Research 2025», 153M LOC; vendor report, not peer-reviewed).
- AI-generated code carries ~1.7× more issues and +75% logic bugs (CodeRabbit «State of AI vs Human Code Generation», Dec 2025, 470 PRs; vendor report, not peer-reviewed).
- AI-generated code share: Google 75% (Pichai, Apr 2026); Microsoft ~30% (Nadella, Apr 2025); industry 15–25% committed lines (Larridin Developer Productivity Hub, 2026).

This protocol does not accept that outcome. **Neuroslop** — code that looks plausible but is architecturally meaningless — accumulates unless the system catches it.

**Outputs**: (a) codebase health, (b) culture of systems-thinking, (c) currency with AI practice. All three are non-contradictory.

**Knowledge transfer goal**: tacit «how to work with AI» knowledge from systems-thinkers (including neurodivergent developers) is formalized into the protocol. The cognitive style: **hyper-systemizing** (Baron-Cohen 2009), **monotropism** (Murray/Lesser/Lawson 2005), **detail-focused processing** (Frith & Happé 2006). The connection to architectural defense is the hypothesis this plugin tests; the eval harness probes it.

## 2. Meta-concepts

Calibration of priors, not imperative rules — the protocol shapes how the AI weighs alternatives.

**Systems theory** — agents, hooks, eval, and developer are connected by feedback loops; drop any layer and equilibrium breaks.

**Game theory** — anchor-verification dominates hallucination; per-mutation gating dominates unauthorised mutation; mutual doubt dominates unilateral fallibility; own-interest cooperation dominates sycophancy.

**Base operational concepts:**
- **Co-system** — AI + developer + a shared artifact. Both err. The system catches errors mutually.
- **AI = hypothesis generator; developer decides and bears responsibility.**
- **Symmetric fallibility (mutual doubt)** — both sides err; epistemic-auditor operationalizes the developer-side detection.
- **Cooperation strategy** — the agent pursues protocol concepts in its own interest; does not capitulate to sycophancy; does not «just do the task» when the task violates the protocol.
- **Common sense + scientific method** — the only admissible roots of any rule.
- **Epistemic boundary** — confirmed (paired with tool output this reply) vs. associative (marked `associated from X, not verified`).
- **Halt on no-progress / contradiction** — third identical attempt stops; contradiction in own words — stop and resolve.
- **Mental-model gate** — act only with 2–3 variants validated against counter-variants.
- **Mutation gate** — every state-changing action requires explicit recent consent.
- **Cultural transmission** — the protocol is operational for the AI and cognitive scaffolding for the developer simultaneously.

**Cross-cutting ideas**: halt on contradiction; fix the binding constraint (compress, not expand); teaching by demonstration — every refusal carries a one-line «why».

**Invariants** in `invariants.txt` — three groups: agent-side, developer-side (mutual doubt), cooperation-strategy. Each carries risk-class `[critical|important|style]`, deontic-class `[O|P|F]`, and a `Counter:` clause. One invariant is sampled **risk-weighted** each turn via `UserPromptSubmit` hook (`scripts/random-invariant.sh`).

**Operational gates:**
- `scripts/random-invariant.sh` — samples one invariant per turn.
- `scripts/cycle-detector.sh` — blocks `Bash`/`Edit`/`Write`/`MultiEdit`/`NotebookEdit` on three identical calls in a row.
- `scripts/auto-critic.sh` — **approval gate**: blocks `git push` and MR-creation tools until `@critic` returns approve.
- `scripts/verification-gate.sh` — **verification gate**: on `git commit`, runs machine-checkable evidence (`bash -n` for shell, `ast.parse` for Python, `jq empty` for JSON) and blocks if any fails. Dual gate per `arXiv:2511.05524` — approval-only ≈ 100% false-completion, verification-only ≈ 25%, dual gate → 0%.
- `scripts/self-review-preflight.sh` — on critical-review prompts, emits a reading-list reminder to prevent inverted sycophancy.

## 3. How to work with the AI as a team

Ten rules. The protocol does the rest.

1. **AI is a hypothesis generator, not an oracle.** Any claim about code requires tool-evidence in the same reply.
2. **Do not give vague prompts.** Concrete anchors (`filename:line`, exact strings, ticket IDs) → fewer hallucinations.
3. **Ask for variants, not «the single right answer».** The AI surfaces 2–3 variants; you converge through your own reasoning.
4. **Before push / MR — call `@critic`.** The auto-critic hook enforces this on `git push` and MR-creation tools.
5. **When in doubt about facts — call `@epistemic-auditor`.** It marks associative vs confirmed; anything tagged `associated from X, not verified` requires manual verification.
6. **If the AI loops, the system stops itself on the 3rd identical attempt** (cycle-detector hook). Reframe the task.
7. **Every turn the AI runs a random self-check** against one invariant from `invariants.txt`.
8. **Decisions and responsibility live with the developer.** Any merged artifact is yours, as if hand-written.
9. **The agent does not capitulate.** If your request violates the protocol — expect a refusal + counter-proposal. That is the cooperation strategy, not stubbornness.
10. **Critical-review is a special case.** On «critically evaluate» / «review» / «assess» prompts, delegate to `@critic` or apply critic-invariants locally. Otherwise **inverted sycophancy** fires — plausible critique without reading the artifact.

## 4. Project intent

This plugin exists so that AI-assisted development *does well and does no harm* — scientifically, through systems-thinking and strategic vision. It is **not a security gate against the agent itself** — it is a co-system calibration tool; the developer remains the decision-maker and responsible party.

It formalizes tacit knowledge of senior systems-thinkers into a protocol, defends the codebase from neuroslop, and develops toward a measurable cumulative effect through two-sided error detection, epistemic discipline, and pre-registered statistical proof that each change improves the whole.

## Agents

Agents are bound to **roles** in the co-system. Names are current bindings; the protocol depends on the role, not the name.

| Binding | Role | Responsibility |
|---|---|---|
| `analyzer` | system investigator | RCA, architecture, MR/PR review, dead-end diagnostics |
| `developer` | code mutator | Code, tests, build, git push — the only mutator |
| `critic` | anti-neuroslop reviewer | Reviews proposed output before it lands in shared state |
| `epistemic-auditor` | epistemic auditor | Boundary between confirmed and associative + developer-side mutual-doubt checks |
| `translator` | codebook translator | Codebook A↔D, RU↔EN for AI-facing files, session condensation, abstraction-ladder rewrite |

Stack specifics can be placed in `references/per-stack/<stack>.md`.

The eval harness — paired Wilcoxon + bootstrap CI on Cohen's d + McNemar one-sided under a pre-registered decision rule — lives in `eval/run_suite.py` and `eval/statistical_test.py`. Binary rubric (18 criteria, MET/UNMET) removes central-tendency bias; `--k N` runs with median aggregation; Krippendorff α on 18 binary criteria raises inter-rater reliability; a canary GUID in every probe + `scripts/check-canary-leak.py` catch contamination. Methodology: 2026 SOTA for rubric-based LLM evaluation.

## Copyright

© 2026 Aleksandr Shchuka. Licensed under the MIT License — see `LICENSE` and `COPYRIGHT-NOTICE.md`.
