#!/usr/bin/env bash
# selftest_random_invariant.sh — regression probe for scripts/random-invariant.sh
#
# Runs random-invariant.sh 300 times with LINES=62 in env (the bash terminal-height
# variable that collides with the old array name) and asserts:
#   (a) every emitted payload line after "> " exists verbatim in invariants.txt
#   (b) when a deontic header is present, the class letter matches the [OPF] tag
#       inside the emitted invariant line
# Exits non-zero on any violation; prints a summary of all failures.
#
# Usage: bash scripts/selftest_random_invariant.sh
# Run from the repository root or any directory; paths are resolved relative to
# this script's own location.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/random-invariant.sh"
INVARIANTS="$HERE/../invariants.txt"

if [[ ! -f "$SCRIPT" ]]; then
  printf 'selftest: ERROR: script not found: %s\n' "$SCRIPT" >&2
  exit 1
fi
if [[ ! -f "$INVARIANTS" ]]; then
  printf 'selftest: ERROR: invariants.txt not found: %s\n' "$INVARIANTS" >&2
  exit 1
fi

RUNS=300
failures=0
pass=0

for i in $(seq 1 "$RUNS"); do
  # Run the script with LINES=62 in env to trigger the collision scenario
  output="$(LINES=62 bash "$SCRIPT" 2>/dev/null)"

  # Extract the invariant payload: the line immediately after "> "
  payload="$(printf '%s\n' "$output" | grep -m1 '^> ' | sed 's/^> //')"

  if [[ -z "$payload" ]]; then
    printf 'FAIL  run %d: no payload line found in output\n' "$i"
    failures=$((failures + 1))
    continue
  fi

  # Assertion (a): payload must exist verbatim in invariants.txt
  if ! grep -qxF "$payload" "$INVARIANTS"; then
    printf 'FAIL  run %d [assertion-a]: payload not found verbatim in invariants.txt:\n  %s\n' \
      "$i" "$payload"
    failures=$((failures + 1))
    continue
  fi

  # Assertion (b): if a deontic header is present, its class letter must match
  # the [OPF] tag inside the payload line
  deontic_header="$(printf '%s\n' "$output" | grep -m1 "^This invariant's deontic class: " || true)"
  if [[ -n "$deontic_header" ]]; then
    # Extract the class letter from the header: "deontic class: X ("
    header_letter="$(printf '%s\n' "$deontic_header" | grep -oP "(?<=deontic class: )[OPF]" || true)"
    # Extract the [OPF] tag from the payload line
    payload_letter="$(printf '%s\n' "$payload" | grep -oP "(?<=\[)[OPF](?=\])" | head -1 || true)"

    if [[ -z "$header_letter" ]]; then
      printf 'FAIL  run %d [assertion-b]: could not parse deontic letter from header:\n  %s\n' \
        "$i" "$deontic_header"
      failures=$((failures + 1))
      continue
    fi
    if [[ -z "$payload_letter" ]]; then
      printf 'FAIL  run %d [assertion-b]: deontic header present but no [OPF] tag in payload:\n  header: %s\n  payload: %s\n' \
        "$i" "$deontic_header" "$payload"
      failures=$((failures + 1))
      continue
    fi
    if [[ "$header_letter" != "$payload_letter" ]]; then
      printf 'FAIL  run %d [assertion-b]: deontic mismatch — header says %s, payload tag is [%s]:\n  payload: %s\n' \
        "$i" "$header_letter" "$payload_letter" "$payload"
      failures=$((failures + 1))
      continue
    fi
  fi

  pass=$((pass + 1))
done

printf '\n'
if [[ "$failures" -gt 0 ]]; then
  printf 'SELFTEST FAILED: %d/%d runs failed (LINES=62 collision probe)\n' "$failures" "$RUNS"
  exit 1
else
  printf 'SELFTEST OK: %d/%d runs passed (LINES=62 collision probe)\n' "$pass" "$RUNS"
  exit 0
fi
