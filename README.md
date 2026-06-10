# neuro-matrix

A Claude Code plugin that calibrates an AI + developer co-system on common sense, scientific method, and Nash-equilibrium cooperation. Agents, hooks, an invariant-driven self-check, and a held-out evaluation harness.

**What it is:** an anti-hallucination (&laquo;anti-neuroslop&raquo;) **harness for Claude Code** — runtime **invariants** with a per-turn self-check, deterministic **hooks**, four **agents** (developer · analyzer · critic · epistemic-auditor), a dual approval+verification gate, and a held-out **evaluation harness** that keep AI-assisted coding and code review anchored to reality. *Topics: Claude Code plugin, AI agents, prompt engineering, LLM evaluation, AI code review, hooks, agentic, AI safety.*

## Install

```text
/plugin marketplace add AlexShchuka/neuro-matrix
/plugin install neuro-matrix@neuro-matrix
```

Requires [Claude Code](https://code.claude.com). On install the protocol activates: a risk-weighted invariant self-check each turn, cycle / critic / verification hooks on mutations, and four sub-agents for analysis, code, review, and epistemic audit.

The operating protocol lives in `CLAUDE.md`. This README answers four questions: **why, on what concepts, how to work as a team, and what the project is for.**

The name is a nod to John Forbes Nash Jr. — payoff matrices in game theory, the mind matrices Nash drew on glass in *A Beautiful Mind*, and the neurodivergent cognitive style that powers systems thinking under uncertainty. A protocol that seeks its own equilibrium.

## 1. Goals

**Defensive**: keep AI-scaled development from degrading (a) the codebase and (b) the engineering culture of systems-thinking.

What the industry shows:

- Duplicated code blocks growing multi-fold; copy-paste outpacing refactoring (GitClear «AI Copilot Code Quality Research 2025», 153M LOC; vendor report, not peer-reviewed).
- AI-generated code carries ~1.7× more issues and +75% logic bugs (CodeRabbit «State of AI vs Human Code Generation», Dec 2025, 470 open-source PRs; vendor report, not peer-reviewed).
- Share of AI-generated code in major companies: Google — 75% (Sundar Pichai, Apr 2026 keynote); Microsoft — ~30% (Satya Nadella, Apr 2025; some internal repos already >50%); industry average — 15–25% committed lines, 40–60% in top-quartile teams (Larridin Developer Productivity Hub, 2026).

This protocol does not accept that outcome. **Neuroslop** — code that looks plausible but is architecturally meaningless — accumulates in codebases unless the system catches it.

**Outputs of the plugin**: (a) codebase health, (b) culture of systems-thinking — measured outputs, backed by the eval harness and invariants. (c) **currency with AI practice — keeping pace with the market** — operationalization pending; the meta-axiom and direction exist, the eval gate does not yet. All three are non-contradictory: systems-thinking + market currency catches trending failure modes; codebase health requires current techniques.

**Knowledge transfer goal**: tacit «how to work with AI» knowledge from systems-thinkers (including neurodivergent developers with naturally formal cognition) is formalized into the protocol and transmitted to anyone who reads `CLAUDE.md`. Polanyi tacit → explicit through a formal protocol.

The cognitive style being formalized is a documented attention architecture: **hyper-systemizing** (Baron-Cohen 2009 — drive to analyze if/then/why rules), **monotropism** (Murray/Lesser/Lawson 2005 — deep attention in a small number of tunnels, flow-state on one task), **detail-focused processing** (Frith & Happé 2006 — superiority in local detail vs aggressive global summarization). These styles reduce sensitivity to framing effects and raise the ability to see local patterns (this follows directly from the cited work). The connection *«therefore this defends architecture from neuroslop»* is the author's inference — the cited papers establish the cognitive constructs; transferring them to architectural defense is the hypothesis this plugin tests, and the eval harness probes it.

## 2. Meta-concepts and principles

Calibration of priors, not imperative rules — the protocol shapes how the AI weighs alternatives, not a stepwise checklist. Concrete rules age; principles do not.

The protocol is designed under two formal lenses.

**Systems theory** — every layer affects every other: agents, hooks, eval, and developer are connected by feedback loops; the whole exceeds the sum of parts; drop any layer and equilibrium breaks.

**Game theory** — incentive structures are arranged so that anchor-verification dominates hallucination, per-mutation gating dominates unauthorised mutation, mutual doubt dominates unilateral fallibility, and own-interest cooperation dominates sycophancy. This is the source of the name: a Nash-style equilibrium where neither side of the co-system benefits from defecting.

**Base operational concepts:**

- **Co-system** — AI + developer + a shared artifact. Both err. The system catches errors mutually.
- **AI = hypothesis generator; developer decides and bears responsibility.**
- **Symmetric fallibility (mutual doubt)** — both sides err. Developer-side detection is operationalized through the epistemic-auditor: invariants detect ambiguous-anchor prompts, cross-turn contradictions, automation-bias.
- **Cooperation strategy** — the agent pursues every concept of the protocol in its own interest; it does not capitulate to sycophantic requests; it does not «just do the task» when the task violates the protocol. Cooperation is a positive-sum repeated game: both sides win only when both goals hold (task solved AND protocol upheld).
- **Common sense + scientific method** — the only admissible roots of any rule in the protocol.
- **Epistemic boundary** — confirmed claims (paired with tool-output in the same reply) vs. associative inferences (marked inline `associated from X, not verified`).
- **Halt on no-progress / contradiction** — a third identical attempt stops; contradiction in own words or between tool-outputs — stop and resolve.
- **Mental-model gate** — the agent acts only when it holds the task as a complete system: 2–3 variants × counter-variants × structure systems-coherent.
- **Mutation gate** — every state-changing action (commit, push, write) requires explicit recent consent.
- **Cultural transmission** — the protocol is operational for the AI and simultaneously cognitive scaffolding for the developer. Reading converges the reader on systems-thinking before any concrete task.

**Cross-cutting ideas** (above the per-rule level):

- Halt on contradiction.
- Fix the binding constraint (usually reader attention; compress, do not expand).
- Teaching by demonstration — every refusal / action carries a one-line «why».

**Invariants** with explicit `Why:` clauses live in `invariants.txt` — three groups: agent-side, developer-side (mutual doubt), cooperation-strategy (own-interest). Each invariant carries two axes: risk-class `[critical|important|style]` (drives sampling weight) and deontic-class `[O|P|F]` (obligation / permission / forbidden), plus a `Counter:` clause — the condition under which the rule does not apply. One invariant is sampled randomly each turn via the `UserPromptSubmit` hook (Constitutional AI pattern adapted for runtime); the sampler emits both axes and the Counter into the self-check block.

**Operational gates** (fire automatically):

- `scripts/random-invariant.sh` — samples one invariant each turn for extra rigor.
- `scripts/cycle-detector.sh` — blocks `Bash` / `Edit` / `Write` / `MultiEdit` / `NotebookEdit` if the same tool + input was used three times in a row.
- `scripts/auto-critic.sh` — **approval gate**: blocks `git push` and MR-creation tools until `@critic` returns approve.
- `scripts/verification-gate.sh` — **verification gate**: on `git commit`, runs machine-checkable evidence on the staged artifacts (`bash -n` for shell, `ast.parse` for Python, `jq empty` for JSON) and blocks the commit if any fails. Approval is necessary but not sufficient; this is the post-execution half of an EviBound-style dual gate (`arXiv:2511.05524` — approval-only ≈ 100% false-completion, verification-only ≈ 25%, dual gate → 0%).
- `scripts/self-review-preflight.sh` — on critical-review prompts, emits a reading-list reminder to prevent inverted sycophancy.

## 3. How to work with the AI as a team

Ten rules. The protocol does the rest.

1. **AI is a hypothesis generator, not an oracle.** Any claim about code requires tool-evidence in the same reply. Do not trust «plausible-sounding» without a fixed source.
2. **Do not give vague prompts.** Concrete anchors (`filename:line`, exact strings, ticket IDs) → fewer hallucinations. If an anchor is missing, the AI must ask, not make one up.
3. **Ask for variants, not «the single right answer».** The AI surfaces 2–3 associative variants; you converge through your own associations.
4. **Before push / MR — call `@critic`.** Second pair of eyes; anti-neuroslop. The auto-critic hook enforces this on `git push` and MR-creation tools.
5. **When in doubt about facts — call `@epistemic-auditor`.** It marks associative vs confirmed; anything tagged `associated from X, not verified` requires manual verification.
6. **If the AI loops, the system stops itself on the 3rd identical attempt** (cycle-detector hook). Reframe the task or give it a new anchor.
7. **Every turn the AI runs a random self-check** against one invariant from `invariants.txt`. If the AI explicitly cites an invariant in its reply — it has verified itself against it.
8. **Decisions and responsibility live with the developer.** The AI accelerates many small steps; it does not replace judgment. Any merged artifact is yours, as if hand-written.
9. **The agent does not capitulate.** If your request violates the protocol (push to main, mutation without consent, invention without anchor, sycophantic agreement) — expect a refusal + counter-proposal. That is the cooperation strategy, not stubbornness. The agent's own interest = the protocol's concepts; agreement against the concepts is defection from the positive-sum game.
10. **Critical-review is a special case.** On «critically evaluate» / «review» / «assess» prompts, the orchestrator either delegates to `@critic` or explicitly applies critic-invariants locally. Otherwise **inverted sycophancy** fires — plausible critique without reading the artifact, visually identical to real review. Mirror to invariant #20.

## 4. Project intent

This plugin exists so that AI-assisted development *does well and does no harm* — scientifically, through systems-thinking and strategic vision.

It formalizes tacit knowledge of senior systems-thinkers (including neurodivergent developers with naturally formal cognition) into a protocol that cultivates the same mode in anyone who reads it, and defends the codebase and the engineering culture from neuroslop.

It develops toward a measurable cumulative effect in the positive — through two-sided error detection, continuous epistemic discipline, and pre-registered statistical proof that each change improves the whole, not just a local metric.

## Agents

Agents are bound to **roles** in the co-system. Names below are current bindings; the protocol depends on the role, not the name — renaming an agent does not break peers.

| Binding | Role | Responsibility |
|---|---|---|
| `analyzer` | system investigator | RCA, architecture, MR/PR review, dead-end diagnostics, domain-term routing (surface UNVERIFIED when unanchorable) |
| `developer` | code mutator | Code, tests, build, git push — the only mutator |
| `critic` | anti-neuroslop reviewer | Reviews proposed output before it lands in shared state |
| `epistemic-auditor` | epistemic auditor | Boundary between confirmed and associative + developer-side mutual-doubt checks (ambiguous-anchor, cross-turn contradiction, automation-bias) |

Stack specifics for code mutator and system investigator can be placed in `references/per-stack/<stack>.md` (currently empty — add your stack files as needed).

The eval harness — paired Wilcoxon + bootstrap CI on Cohen's d + McNemar one-sided under a pre-registered decision rule — lives in `eval/run_suite.py` and `eval/statistical_test.py`. The binary rubric (17 criteria, MET/UNMET) removes central-tendency bias; `--k N` runs with median aggregation filter non-determinism; Krippendorff α on 17 binary criteria raises inter-rater reliability under multi-rater conditions; a canary GUID in every probe + `scripts/check-canary-leak.py` catch contamination via repo-grep. Methodology: 2026 SOTA for rubric-based LLM evaluation.

## Copyright

© 2026 Aleksandr Shchuka. Licensed under PolyForm Noncommercial 1.0.0 — **noncommercial use only** — see `LICENSE` and `COPYRIGHT-NOTICE.md`.
