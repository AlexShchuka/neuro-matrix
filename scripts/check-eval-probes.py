#!/usr/bin/env python3
"""Validate Layer E eval probe files (CI gate).

Checks every eval/questions/q*.md and eval/adversarial/adv*.md:
  - has a non-empty `## Prompt` section. run_suite.py raises at runtime on a
    missing one — catch it here, at commit time, instead.
  - has a `## Canary` section containing a UUID-shaped GUID.
  - all canary GUIDs are globally unique across the suite.
  - the canary GUID does NOT appear in the probe's own `## Prompt` body — a leak
    there would contaminate the held-out measurement (the same property
    check-canary-leak.py enforces on responses, enforced here at the source).

Exit 0 if every probe is valid; nonzero with a single machine-readable FAIL
line on the first violation. stdlib only, deterministic, no network.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_SECTION = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def section(text: str, name: str) -> str:
    matches = list(_SECTION.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == name.lower():
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[start:end].strip()
    return ""


def fail(code: str, where: str, reason: str) -> None:
    print(f"FAIL {code} [{where}]: {reason}")
    sys.exit(1)


def main() -> int:
    probes = sorted((REPO / "eval" / "questions").glob("q*.md")) + sorted(
        (REPO / "eval" / "adversarial").glob("adv*.md")
    )
    if not probes:
        fail("EMPTY", "eval", "no probe files found")

    seen: dict[str, str] = {}
    for path in probes:
        where = path.relative_to(REPO).as_posix()
        text = path.read_text(encoding="utf-8")

        prompt = section(text, "Prompt")
        if not prompt:
            fail("PROMPT", where, "missing or empty `## Prompt` section")

        canary_body = section(text, "Canary")
        if not canary_body:
            fail("CANARY", where, "missing `## Canary` section")
        m = _UUID.search(canary_body)
        if not m:
            fail("CANARY", where, "`## Canary` has no UUID-shaped GUID")
        guid = m.group(0)

        if guid in seen:
            fail("DUP", where, f"canary GUID {guid} also used in {seen[guid]}")
        seen[guid] = where

        if guid in prompt:
            fail(
                "LEAK", where,
                "canary GUID appears in the `## Prompt` body — it would leak "
                "into the model input and contaminate the held-out probe",
            )

    print(f"OK: {len(probes)} eval probes valid ({len(seen)} unique canaries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
