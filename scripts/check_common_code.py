#!/usr/bin/env python3
"""check_common_code.py - deterministic validator for the A/D Common Code interchange file.

Validates a shared three-sided records file (JSONL, one record per line). It checks,
fail-closed, that the file can be trusted WITHOUT reading its content and WITHOUT an LLM:

  (a) SHAPE      each record is the three-sided object
                 {id, a_view, d_view, science_anchor{text, source, tag}, verdict, signed_by}
                 tag in {FACT, ANALOGY, HYPO, UNVERIFIED}; verdict in {MATCH, DIVERGE}
                 a FACT tag requires a non-empty source token (anchored fact rule)
                 signed_by: JSON array, subset of {"A","D"}, no duplicates
  (b) BUDGET     hard volume caps  N_inv <= 30 ; per-cell length <= MAX_CELL chars
                 (anti-neuroslop: irrelevant/excess context degrades the AI -
                  Shi et al. 2023 arXiv:2302.00093 ; Iratni et al. 2025 arXiv:2512.14313 ;
                  Liu et al. 2023 arXiv:2307.03172 lost-in-the-middle)
  (c) INTEGRITY  canonical serialization (sorted-key canonical JSON, RFC 8785 / JCS-STYLE)
                 + SHA-256 over the canonical byte form, so A and D can confirm they hold
                 the BYTE-IDENTICAL state. RFC 8785 (JCS): deterministic lexicographic key
                 sorting -> same digest across runtimes. NOTE: this uses Python stdlib
                 json with sort_keys (JCS-STYLE); it is NOT strict RFC 8785 number
                 serialization. All record fields here are strings, so the difference does
                 not bite; do not feed floats and expect cross-language byte-identity.
  (d) RETRIEVAL  a source/retrieval pointer must be present on every record
                 (Clark & Chalmers 1998 'easily retrievable' criterion, proxied: an anchor
                  whose source you cannot retrieve is noise and is dropped -> fail closed).
  (e) SIGNATURE  verdict MATCH requires signed_by to contain BOTH "A" and "D"
                 (ADR-003 §3 cross-side rule; the non-producing human signs before MATCH).

Exit 0 with the canonical SHA-256 on success; nonzero with a single machine-readable
FAIL line (FAIL <code> [record <id-or-line>]: <reason>) on the first violation.

stdlib only, deterministic, no network. Usage: check_common_code.py <file.jsonl>
"""
import sys
import json
import hashlib

N_INV_MAX = 30          # hard cap on number of invariant rows (volume budget)
MAX_CELL = 280          # hard cap on per-cell character length (volume budget)
TAGS = {"FACT", "ANALOGY", "HYPO", "UNVERIFIED"}
VERDICTS = {"MATCH", "DIVERGE"}
VALID_SIGNERS = {"A", "D"}
CELL_FIELDS = ("id", "a_view", "d_view", "verdict")
REQUIRED = ("id", "a_view", "d_view", "science_anchor", "verdict", "signed_by")
ANCHOR_FIELDS = ("text", "source", "tag")


def fail(code, reason, where=""):
    loc = f" {where}" if where else ""
    print(f"FAIL {code}{loc}: {reason}")
    sys.exit(1)


def canonical_bytes(records):
    """RFC 8785 / JCS-style canonical form: each record sorted-key, no spaces, NL-joined."""
    lines = [
        json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for r in records
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def main():
    if len(sys.argv) != 2:
        fail("ARGS", "usage: check_common_code.py <file.jsonl>")
    path = sys.argv[1]
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.readlines()
    except OSError as exc:
        fail("IO", f"cannot read file: {exc}")

    records = []
    seen_ids = set()
    for lineno, line in enumerate(raw, 1):
        s = line.strip()
        if not s or s.startswith("#"):          # blank / comment line
            continue
        try:
            rec = json.loads(s)
        except json.JSONDecodeError as exc:
            fail("JSON", f"not valid JSON: {exc}", f"line {lineno}")
        if not isinstance(rec, dict):
            fail("SHAPE", "record is not a JSON object", f"line {lineno}")

        for key in REQUIRED:
            if key not in rec:
                fail("SHAPE", f"missing field '{key}'", f"line {lineno}")
        extra = set(rec) - set(REQUIRED)
        if extra:
            fail("SHAPE", f"unexpected field(s) {sorted(extra)}", f"line {lineno}")

        rid = rec["id"]
        where = f"record {rid!r}"
        for key in CELL_FIELDS:
            if not isinstance(rec[key], str) or not rec[key].strip():
                fail("SHAPE", f"field '{key}' must be a non-empty string", where)
            if len(rec[key]) > MAX_CELL:
                fail("BUDGET", f"field '{key}' exceeds {MAX_CELL} chars (volume cap)", where)
        if rid in seen_ids:
            fail("SHAPE", f"duplicate id {rid!r}", where)
        seen_ids.add(rid)

        if rec["verdict"] not in VERDICTS:
            fail("SHAPE", f"verdict must be one of {sorted(VERDICTS)}", where)

        # (a) signed_by: must be a JSON array, subset of {"A","D"}, no duplicates
        sb = rec["signed_by"]
        if not isinstance(sb, list):
            fail("SHAPE", "signed_by must be a JSON array", where)
        for item in sb:
            if not isinstance(item, str):
                fail("SHAPE", "signed_by elements must be strings", where)
            if item not in VALID_SIGNERS:
                fail("SHAPE",
                     f"signed_by element {item!r} not in {sorted(VALID_SIGNERS)}", where)
        if len(sb) != len(set(sb)):
            fail("SHAPE", "signed_by contains duplicates", where)

        # (e) SIGNATURE: MATCH requires both "A" and "D" in signed_by
        if rec["verdict"] == "MATCH":
            if "A" not in sb or "D" not in sb:
                fail("SIGNATURE",
                     "verdict MATCH requires signed_by to contain both 'A' and 'D'", where)

        anchor = rec["science_anchor"]
        if not isinstance(anchor, dict):
            fail("SHAPE", "science_anchor must be an object", where)
        for key in ANCHOR_FIELDS:
            if key not in anchor:
                fail("SHAPE", f"science_anchor missing '{key}'", where)
        extra_a = set(anchor) - set(ANCHOR_FIELDS)
        if extra_a:
            fail("SHAPE", f"science_anchor unexpected field(s) {sorted(extra_a)}", where)
        for key in ANCHOR_FIELDS:
            if not isinstance(anchor[key], str):
                fail("SHAPE", f"science_anchor.{key} must be a string", where)
            if len(anchor[key]) > MAX_CELL:
                fail("BUDGET", f"science_anchor.{key} exceeds {MAX_CELL} chars", where)
        if anchor["tag"] not in TAGS:
            fail("SHAPE", f"science_anchor.tag must be one of {sorted(TAGS)}", where)
        # (d) retrieval pointer: every anchor must carry a retrievable source.
        if not anchor["source"].strip():
            fail("RETRIEVAL", "science_anchor.source empty (not retrievable - drop)", where)
        # anchored-fact rule: a FACT claim must name its source.
        if anchor["tag"] == "FACT" and not anchor["source"].strip():
            fail("ANCHOR", "[FACT] tag requires a non-empty source", where)
        records.append(rec)

    n = len(records)
    if n == 0:
        fail("EMPTY", "no records found")
    if n > N_INV_MAX:
        fail("BUDGET", f"{n} invariants > cap {N_INV_MAX} (volume budget)")

    digest = hashlib.sha256(canonical_bytes(records)).hexdigest()
    print(f"OK: {n} invariants, shape+budget+anchors valid")
    print(f"SHA-256(canonical) = {digest}")
    sys.exit(0)


if __name__ == "__main__":
    main()
