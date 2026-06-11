# Common Code v3 — Oracle split, glossary grounding, signed table

Status: **PROPOSED for A/D acceptance — accepted only after D returns a paraphrase.**
Supersedes ADR-002. Scope: communication system only.

## BLUF

v2 named the human oracle but left the mechanizable/judgment boundary implicit. v3 makes
the split explicit, fixes the Perez 2022 misattribution from v2 §0, anchors the glossary
against the symbol-grounding problem, gives the table a third repository with per-column
write ownership (no merge conflict by construction), and adds `signed_by` so MATCH
requires both human signatures as a hard script check — not a prose rule.

## 0. Corrected citation — Perez 2022

v2 §0 stated Perez 2022 shows sycophancy is "inverse-scaling." The abstract of
arXiv:2212.09251 shows sycophancy **scales with model size**; its RLHF inverse-scaling
examples are political-view expression and shutdown avoidance — not sycophancy. Corrected
here. **Sharma 2023 (arXiv:2310.13548) stands unchanged.** Both papers still converge:
RLHF-tuned models are unreliable arbiters of their own correctness; the protocol
consequence is unchanged.

## 1. Oracle split: mechanizable vs judgment

**Mechanizable (pseudo-oracles sufficient):** math/scripts/reality can confirm the
property without a human reading the output (Davis & Weyuker 1981; Claessen & Hughes 2000
QuickCheck; Segura et al. 2016 IEEE TSE metamorphic testing). **Limit:** Knight & Leveson
1986 — 27 independently-written versions, independence hypothesis rejected at 99%
(z=100.51): checkers derived from the same understanding fail dependently. A test written
by your AI from your understanding is not an independent witness. Scripts handle structure;
they cannot confirm intent is captured.

**Judgment class (no non-human validator):** "Did A and D mean the same?" — Barr et al.
2015 abstract-level finding (four-way taxonomy unverified — not cited): "the final source
of test oracle information remains the human." No script resolves semantic convergence.

**Cross-side rule (unchanged):** D validates A's artifacts; A validates D's.
NASA IV&V: neither developer nor acquirer validates their own work.

## 2. Glossary grounding

A glossary is a symbol system — it cannot validate itself. Grounding must come from
outside it. **Vincent-Lamarre et al. 2016:** ~10% of a dictionary defines the rest;
minimal grounding set ≈1%. The kernel is internally circular; grounding requires
non-symbolic referents. **Harnad 1990 (symbol grounding):** symbols acquire meaning
through examples/tests/observations — which is the `science_anchor.source` field.
An anchor with no retrievable source is ungrounded (Clark & Chalmers 1998 retrievability).
**Goodhart (Manheim & Garrabrant 2018, arXiv:1803.04585):** glossary is a harder-to-game
proxy than row count, but still a proxy. Mitigated by `science_anchor` + cross-side
signature; not escaped.

## 3. Table home and schema

**Third repository** writable by both; protected branch requiring counterparty review;
signed commits. **Per-column write ownership (Shapiro et al. 2011 — trivially
conflict-free CRDT corner):** `a_view` written only by A; `d_view` only by D; `verdict`
derived by script from `signed_by` — write conflicts impossible by construction.

**`signed_by` schema addition:** JSON array, subset of `{"A","D"}`, no duplicates.
`verdict: MATCH` requires both "A" and "D" → script FAIL SIGNATURE if absent.
`verdict: DIVERGE` allows any `signed_by` including empty. SHA-256 receipts = divergence
DETECTION, not arbitration (RFC 6962 / Certificate Transparency analogy).

**False-match cost >> false-diverge cost:** MATCH is expensive (both signatures + anchor);
DIVERGE is cheap and unpunished — the asymmetry is intentional.

## 4. Row lifecycle and meeting rhythm

**DNA pipeline:** VARIATION (personal columns — only disputed rows need both views) →
SELECTION (external anchor: test/math/works-in-reality) → FIXATION (depersonalized
"neuro-matrix invariant," owner-independent) → EXPRESSION (invariant compiles into
skill/hook/eval/code/agent) → DELETION (cap-and-graduate, N_inv ≤ 30).

**Live-meeting rhythm:** a conversation produces row *candidates*, not verdicts. After the
meeting each side independently writes its column from memory. Script compares; DIVERGE
rows become the next meeting's agenda. Bainbridge 1983 (vigilance ~30 min, "Bainbridge,
after Mackworth") remains the rationale for capping frequency.

## 5. Falsifiable prediction [HYPO]

**HYPO:** systems-thinking invariants increase the precision of AI associative
command-following. Metric: «не то» cycles per accepted decision (Э-series from v1 §7).
Falsified if DIVERGE-to-MATCH rate does not improve after the third repository goes live.

## 6. Self-applicability

BLUF first; Perez corrected with quoted evidence; oracle split explicit; glossary grounding
sourced; table mechanism concrete; lifecycle named; meeting rhythm operational; falsifiable
prediction present. `signed_by` is a hard script check. If `check_common_code.py` rejects
the sample in `scripts/fixtures/good.jsonl` this ADR has failed and must be cut further.

## 7. Honesty ledger

- [FACT, definitional]: DPI (Cover & Thomas §2.8); symbol grounding (Harnad 1990).
- [FACT, ≥2 sources]: sycophancy from RLHF — Sharma 2023 + Perez 2022 (corrected).
- [FACT, single source]: Knight & Leveson 1986 (z=100.51, 27 versions) — one study, no
  second replication cited here; weight accordingly. Vincent-Lamarre 2016 kernel ~10%.
- [ANALOGY]: Shapiro 2011 CRDT → single-writer table (conflict-freedom is structural).
- [HYPO]: §5 prediction — not yet measured.
- [UNVERIFIED]: Barr 2015 four-way taxonomy (abstract finding cited; taxonomy excluded).

## 8. Sources

Cover & Thomas 2006 §2.8 · Harnad 1990 *Psych. Rev.* 99(2) · Sharma 2023
arXiv:2310.13548 · Perez 2022 arXiv:2212.09251 (corrected) · Knight & Leveson 1986
*Commun. ACM* 29(6):549–558 · Davis & Weyuker 1981 · Claessen & Hughes 2000 ICFP ·
Segura et al. 2016 *IEEE TSE* 42(9) · Barr et al. 2015 *IEEE TSE* 41(1) [abstract only] ·
Vincent-Lamarre et al. 2016 *Psychon. Bull. Rev.* 23(5) · Manheim & Garrabrant 2018
arXiv:1803.04585 · Shapiro et al. 2011 *CACM* 54(1) · RFC 6962 ·
Clark & Chalmers 1998 *Analysis* 58(1) · Bainbridge 1983 *Automatica* 19(6):775–779 ·
NASA IV&V (swehb.nasa.gov SWE-141)
