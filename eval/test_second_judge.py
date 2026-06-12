#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("ci_eval", os.path.join(_HERE, "ci_eval.py"))
ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci)


class _FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_rater_in_csv_schema():
    assert "rater" in ci.CSV_COLS
    assert "rater" in ci.LEGACY_CSV_COLS


def test_github_models_request_and_parse():
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["auth"] = req.get_header("Authorization")
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp({"choices": [{"message": {"content": "JUDGE-JSON"}}]})

    orig = urllib.request.urlopen
    os.environ["GITHUB_TOKEN"] = "tok123"
    urllib.request.urlopen = fake_urlopen
    try:
        out = ci.call_github_models("score this", "openai/gpt-4.1")
    finally:
        urllib.request.urlopen = orig

    assert out == "JUDGE-JSON"
    assert captured["url"] == "https://models.github.ai/inference/chat/completions"
    assert captured["method"] == "POST"
    assert captured["auth"] == "Bearer tok123"
    assert captured["body"]["model"] == "openai/gpt-4.1"
    assert captured["body"]["messages"][0]["content"] == "score this"


def test_github_models_requires_token():
    orig = os.environ.pop("GITHUB_TOKEN", None)
    try:
        raised = False
        try:
            ci.call_github_models("x", "openai/gpt-4.1")
        except RuntimeError:
            raised = True
        assert raised
    finally:
        if orig is not None:
            os.environ["GITHUB_TOKEN"] = orig


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
