# Research anchors — catalogued sources with freshness metadata

Single source of truth for external references that underpin the plugin's protocol. References live here as plain identifiers (not URLs); freshness metadata tracks which anchors are verified vs pending vs deprecated without re-googling.

The catalog is a standalone registry. The `Used in` column maps each row to layer numbers (L1–L10), meta-axiom numbers, and R-vector numbers from a separate development-roadmap document maintained outside this repository; these identifiers are forward-references — a roadmap row may not exist yet, but the anchor stands on its own as a source citation.

## Row format

| Column | Meaning |
|---|---|
| **ID** | Primary identifier — arXiv ID (`arXiv:NNNN.NNNNN`), PMC ID, MDPI / journal `vol/issue`, conference paper slug, or stable identifier for industry sources. |
| **Title** | Short title (paper / report / venue). |
| **Year** | First-publication year. |
| **Type** | `peer-reviewed` / `preprint` / `industry` / `blog` / `venue` (conference / workshop). |
| **Status** | `active` — read in-thread, claim verified against source. `pending-verification` — cited but not yet verified in-thread. `deprecated` — retracted, superseded, or otherwise no longer load-bearing. |
| **Added** | YYYY-MM-DD — when the anchor entered the catalog. |
| **Last-verified** | YYYY-MM-DD — when the anchor was last fetched and the cited claim re-checked. `—` if never verified in-thread. |
| **Used in** | L-layer numbers (L1–L10), meta-axiom numbers, or R-vector numbers (R1–R37 and growing) tracked in a separate development-roadmap document; or a protocol-file section if used outside the roadmap. |

## Maintenance cadence

- **Quarterly review.** Walk the table; for every row with `Last-verified` empty or older than 90 days, attempt in-thread verification (fetch abstract, re-check the specific claim used in the citing layer). Update `Last-verified` to the review date if the claim still stands; flip `Status → deprecated` if retracted / superseded.
- **On every new anchor.** Add a row with `Status: pending-verification`, `Added: <today>`, `Last-verified: —`. The first in-thread verification flips status to `active`.
- **On deprecation.** Do NOT delete the row; set `Status: deprecated` and append `Replaced-by: <id>` if a newer anchor replaces it. Preserves history for re-evaluation.
- **On layer addition.** When a new L-layer or R-vector is added to the external roadmap, its anchors land here first, then the roadmap cites by ID.
- **Automation candidate.** A periodic script can walk this table, query arXiv abstracts to detect retraction notices and bump dates, surface stale entries to the maintainer (R24 in the external roadmap).

## Catalog

### Game theory + mechanism design — used by L1, L6

| ID | Title | Year | Type | Status | Added | Last-verified | Used in |
|---|---|---|---|---|---|---|---|
| arXiv:2507.09407 | Stackelberg-LLM with conjectural equilibria | 2025 | preprint | pending-verification | 2026-05-23 | — | L1 |
| arXiv:2505.13636 | Peer Elicitation Games (PEG) | 2025 | preprint | pending-verification | 2026-05-23 | — | L6 |
| arXiv:2510.08872 | GTAlign — payoff-matrix in reasoning | 2025 | preprint | pending-verification | 2026-05-23 | — | L6 |
| arXiv:2601.23211 | Multi-Agent Systems as Principal-Agent Problems | 2026 | preprint | pending-verification | 2026-05-23 | — | L6 |
| arXiv:2504.03255 | Principal-agent failure taxonomy in LLM MAS | 2025 | preprint | pending-verification | 2026-05-23 | — | L6 |
| ACM-EC-2026/llm-incentives | Game Theory and Mechanism Design with LLMs (workshop) | 2026 | venue | pending-verification | 2026-05-23 | — | L6 |
| arXiv:2603.28063 | Reward Hacking as Equilibrium under Finite Evaluation | 2026 | preprint | pending-verification | 2026-05-23 | — | L6 |
| arXiv:2508.02087 | When Truth Is Overridden — sycophancy as structural override (AAAI 2026) | 2025 | preprint → peer-reviewed | pending-verification | 2026-05-23 | — | L6 |
| arXiv:2603.16643 | Good Arguments Against the People Pleasers — reasoning masks sycophancy | 2026 | preprint | pending-verification | 2026-05-23 | — | L6 |

### Systems / CAS / phase transition — used by L2, L5

| ID | Title | Year | Type | Status | Added | Last-verified | Used in |
|---|---|---|---|---|---|---|---|
| arXiv:2604.19827 | More Is Different — CAS framework for AI-native software | 2026 | preprint | pending-verification | 2026-05-23 | — | L2 |
| arXiv:2512.02329 | Normative MAS for SE teams (BDI + deontic) — Dam et al. | 2025 | preprint | pending-verification | 2026-05-23 | — | L2, L3 |
| arXiv:2511.17332 | Agentifying Agentic AI — Dignum & Dignum | 2025 | preprint | pending-verification | 2026-05-23 | — | L2 |
| arXiv:2601.15077 | Multi-agent constraint factorization (operator-theoretic) | 2026 | preprint | pending-verification | 2026-05-23 | — | L2 |
| arXiv:2601.17311 | Multi-agent phase transition — help / saturate / collapse | 2026 | preprint | pending-verification | 2026-05-23 | — | L5 |
| arXiv:2603.07972 | Metacognitive Policy Optimization for Multi-Agent LLMs | 2026 | preprint | pending-verification | 2026-05-23 | — | L2 |
| arXiv:2510.25595 | Communication-free agent collaboration | 2025 | preprint | pending-verification | 2026-05-23 | — | L2 |

### Deontic + constrained MDP — used by L3

| ID | Title | Year | Type | Status | Added | Last-verified | Used in |
|---|---|---|---|---|---|---|---|
| arXiv:2506.06959 | Deontically Constrained Policy Improvement | 2025 | preprint | pending-verification | 2026-05-23 | — | L3 |

### ODE / control theory — used by L4, L7

| ID | Title | Year | Type | Status | Added | Last-verified | Used in |
|---|---|---|---|---|---|---|---|
| arXiv:2605.06347 | Coupled ODE for human-AI co-evolution | 2026 | preprint | pending-verification | 2026-05-23 | — | L4 |
| arXiv:2603.10779 | Control-theoretic foundation for agentic systems | 2026 | preprint | pending-verification | 2026-05-23 | — | L7 |
| arXiv:2510.13727 | From Refusal to Recovery (IASEAI 2026) | 2025 | preprint | pending-verification | 2026-05-23 | — | L7 |
| arXiv:2503.18666 | AgentSpec declarative runtime DSL (ICSE 2026) | 2025 | preprint → peer-reviewed | pending-verification | 2026-05-23 | — | L7, R15 |
| arXiv:2603.16586 | Runtime governance via paths | 2026 | preprint | pending-verification | 2026-05-23 | — | L7 |
| arXiv:2509.09265 | Entropy-Modulated Policy Gradients | 2025 | preprint | pending-verification | 2026-05-23 | — | L7 |

### Chaos / dynamical systems — used by L8

| ID | Title | Year | Type | Status | Added | Last-verified | Used in |
|---|---|---|---|---|---|---|---|
| arXiv:2512.10350 | Geometric Dynamics of Agentic Loops | 2025-2026 | preprint | pending-verification | 2026-05-23 | — | L8 |
| arXiv:2603.29231 | Capability-tier meltdown attractor | 2026 | preprint | pending-verification | 2026-05-23 | — | L8, R9 |
| arXiv:2511.09710 | Salesforce "echoing" / role-collapse | 2025 | preprint | pending-verification | 2026-05-23 | — | L1, L8 |
| arXiv:2601.04170 | Agent Stability Index | 2026 | preprint | pending-verification | 2026-05-23 | — | L8, R5 |
| arXiv:2505.03096 | Cascading faults in multi-LLM systems | 2025 | preprint | pending-verification | 2026-05-23 | — | L5 |
| arXiv:2505.11584 | LLM agents hypersensitive to nudges (ICLR 2026) | 2025 | preprint → peer-reviewed | pending-verification | 2026-05-23 | — | L8 |
| arXiv:2603.09127 | Collective amplification of tiny perturbations | 2026 | preprint | pending-verification | 2026-05-23 | — | L8 |
| arXiv:2602.01288 | EDIS — Entropy Dynamics Instability Score | 2026 | preprint | pending-verification | 2026-05-23 | — | L8, R16 |
| arXiv:2603.18940 | Entropy-trajectory monotonicity predicts CoT reliability | 2026 | preprint | pending-verification | 2026-05-23 | — | L8, R16 |

### Variance decomposition — used by L9

| ID | Title | Year | Type | Status | Added | Last-verified | Used in |
|---|---|---|---|---|---|---|---|
| arXiv:2601.21339 | Within-Model vs Between-Prompt Variability | 2026 | preprint | pending-verification | 2026-05-23 | — | L9 |
| arXiv:2506.10204 | Code Roulette — structural cross-entropy on AST (ICSE LLM4Code 2026) | 2025 | preprint → peer-reviewed | pending-verification | 2026-05-23 | — | L9 |

### Cultural transmission / cognitive — used by L10

| ID | Title | Year | Type | Status | Added | Last-verified | Used in |
|---|---|---|---|---|---|---|---|
| arXiv:2601.19053 | Cognitive Apprenticeship for LLM mentors (CHI 2026) | 2026 | peer-reviewed | pending-verification | 2026-05-23 | — | L10 |
| arXiv:2603.21735 | Cognitive Agency Surrender / Scaffolded AI Friction | 2026 | preprint | pending-verification | 2026-05-23 | — | L7, L10, R34 |
| MDPI/Information/vol16/issue11/1009 | Cognitive Sustainability Index (Kabashkin) | 2025 | peer-reviewed | pending-verification | 2026-05-23 | — | L10, R6 |
| MDPI/Information/2025/cognitive-atrophy | Cognitive Atrophy Paradox of AI–Human Interaction | 2025 | peer-reviewed | pending-verification | 2026-05-23 | — | L10 |
| arXiv:2603.26707 | Cognitive Divergence — human Effective Context Span contraction | 2026 | preprint | pending-verification | 2026-05-23 | — | L10 |
| arXiv:2603.18677 | Cognitive Amplification vs Delegation | 2026 | preprint | pending-verification | 2026-05-23 | — | L10 |
| PMC12824279 | Divergent creativity humans vs LLMs (Scientific Reports) | 2026 | peer-reviewed | pending-verification | 2026-05-23 | — | L10 |
| arXiv:2410.03703 | Human Creativity in the Age of LLMs (CHI 2025) — Doshi & Hauser | 2025 | peer-reviewed | pending-verification | 2026-05-23 | — | L10 |
| BCG-Harvard-MIT-Wharton-2026 | Centaurs and Cyborgs follow-up (working paper) | 2026 | industry | pending-verification | 2026-05-23 | — | L10 |
| industry-2025-2026/senior-19pp-slowdown | Senior developer 19% slowdown with AI on complex tasks (reportedly methodologically retracted 2026-02; retraction itself `pending-verification`) | 2025-2026 | industry | deprecated | 2026-05-23 | — | L10 (prose-ref only) |

### Methodology / eval

| ID | Title | Year | Type | Status | Added | Last-verified | Used in |
|---|---|---|---|---|---|---|---|
| arXiv:2603.00077 | LLM-judge rubric central-tendency bias | 2026 | preprint | pending-verification | 2026-05-23 | — | eval/criteria.md |
| ConfidentAI-guide-2026/krippendorff-alpha | Krippendorff α multi-rater (Confident AI guide) | 2026 | blog | pending-verification | 2026-05-23 | — | eval/criteria.md, R22 |

### Verification gates / two-layer governance — used by R33 (2026-05 additions)

| ID | Title | Year | Type | Status | Added | Last-verified | Used in |
|---|---|---|---|---|---|---|---|
| arXiv:2511.05524 | EviBound — Dual Governance Gates (Approval + Verification) | 2025 | preprint | active | 2026-05-25 | 2026-05-31 | R33, scripts/verification-gate.sh |
| arXiv:2604.08401 | SAVeR — Self-Audited Verified Reasoning before commit | 2026 | preprint | active | 2026-05-25 | 2026-05-31 | R33, scripts/verification-gate.sh |
| arXiv:2603.13189 | CMAG — Constitutional Multi-Agent Governance (hard + soft constraints, ECS metric) | 2026 | preprint | pending-verification | 2026-05-25 | — | R33 |
| arXiv:2505.15182 | ReflAct — Goal-State Reflection for agentic loops | 2025 | preprint | pending-verification | 2026-05-25 | — | R33 |

> **In-thread verification (2026-05-31), operationalized in `scripts/verification-gate.sh`.** EviBound (`arXiv:2511.05524`, *Evidence-Bound Autonomous Research: A Governance Framework for Eliminating False Claims*) reports a pre-execution **Approval Gate** + post-execution **Verification Gate**; measured hallucination (claimed-but-unverified completion): approval/prompt-level-only ≈ 100% (8/8 claimed, 0/8 verified), verification-only ≈ 25%, dual gate → **0%** at ≈ 8.3% execution overhead. SAVeR (`arXiv:2604.08401`, *Verify Before You Commit: Towards Faithful Reasoning in LLM Agents via Self-Auditing*) frames the commit boundary as self-auditing belief-states before action commitment. These two figures back the `active` / `Last-verified: 2026-05-31` rows above and the result numbers cited in `README.md`, `invariants.txt`, and the script header.

### MCP trust + memory governance — used by R30, R31 (2026-05 additions)

| ID | Title | Year | Type | Status | Added | Last-verified | Used in |
|---|---|---|---|---|---|---|---|
| arXiv:2602.14281 | MCPShield — adaptive trust calibration via three-stage closed-loop | 2026 | preprint | pending-verification | 2026-05-25 | — | R30 |
| arXiv:2604.16548 | Long-term memory security / Mnemonic Sovereignty survey | 2026 | preprint | pending-verification | 2026-05-25 | — | R30 |
| arXiv:2601.17019 | Decision Coherence Law / Context Lake (Composition Impossibility Theorem) | 2026 | preprint | pending-verification | 2026-05-25 | — | R31 |

### Externalization + cognitive scaffolding — used by axiom 4, R34 (2026-05 additions)

| ID | Title | Year | Type | Status | Added | Last-verified | Used in |
|---|---|---|---|---|---|---|---|
| arXiv:2604.08224 | Externalization in LLM Agents — cognitive artifacts framework | 2026 | preprint | pending-verification | 2026-05-25 | — | meta-axiom 4 |
| arXiv:2602.20206 | Mitigating Epistemic Debt via metacognitive scripts (N=78 between-subjects) | 2026 | preprint | pending-verification | 2026-05-25 | — | R34 |
| arXiv:2511.02736 | Autism in Software Engineering (Stack Overflow Survey 2022 analysis) | 2025 | preprint | pending-verification | 2026-05-25 | — | R35 |
