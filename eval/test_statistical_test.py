#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os

ALPHA = 0.05

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "statistical_test", os.path.join(_HERE, "statistical_test.py")
)
st = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(st)


def _clear(regressions, improvements):
    b = [1.0] * regressions + [0.0] * improvements
    c = [0.0] * regressions + [1.0] * improvements
    return b, c


def test_counts_match_input():
    assert st.mcnemar_one_sided(*_clear(5, 0))[:2] == (5, 0)
    assert st.mcnemar_one_sided(*_clear(0, 5))[:2] == (0, 5)


def test_regressions_are_flagged():
    _, _, p = st.mcnemar_one_sided(*_clear(5, 0))
    assert abs(p - 0.03125) < 1e-12
    assert p < ALPHA


def test_improvements_are_not_flagged():
    _, _, p = st.mcnemar_one_sided(*_clear(0, 5))
    assert p == 1.0
    assert p >= ALPHA


def test_mass_regression_strongly_flagged():
    _, _, p = st.mcnemar_one_sided(*_clear(11, 0))
    assert abs(p - 1.0 / 2048) < 1e-12
    assert p < ALPHA


def test_tie_not_flagged():
    _, _, p = st.mcnemar_one_sided(*_clear(3, 3))
    assert abs(p - 0.65625) < 1e-12
    assert p >= ALPHA


def test_no_discordant_pairs():
    assert st.mcnemar_one_sided([1.0, 1.0], [1.0, 1.0]) == (0, 0, 1.0)


def test_monotone_in_regressions():
    ps = [st.mcnemar_one_sided(*_clear(r, 5 - r))[2] for r in range(6)]
    assert all(ps[i] >= ps[i + 1] for i in range(len(ps) - 1))


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
