# Python — per-stack operational rules

Read before writing or investigating Python. If a command below has no target in the repo (no config file), **detect, don't assume**; if detection fails, **escalate — do not invent** (per `agents/developer.md` STACK CONTEXT).

## Entry-point & search heuristics
- Executable entry: `if __name__ == "__main__":` blocks; `[project.scripts]`/`console_scripts` in `pyproject.toml`/`setup.cfg`; `__main__.py` in a package; a top-level `main.py`/`app.py`/`cli.py`.
- Package root: the dir holding `__init__.py` (or, for PEP 420 namespace packages, the dir named under `[tool.*]` in `pyproject.toml`).
- Imports map the call graph: `grep -rn "^\(from\|import\) "`; tests live in `tests/` or `test_*.py`/`*_test.py`.

## Build / dependency commands  (detect the manager first)
- `pyproject.toml` → `uv sync` (if `uv.lock`) · `poetry install` (if `[tool.poetry]`) · else `pip install -e .`.
- `requirements*.txt` → `pip install -r <file>`.
- `setup.py`/`setup.cfg` only → `pip install -e .`.
- Prefer an isolated env: `python3 -m venv .venv && . .venv/bin/activate` (or `uv venv`). Never `pip install` into system Python.
- No config at all (scripts run directly, e.g. this repo) → no build step; run modules with `python3 path/to/script.py`.

## Test-execution rules + caps
- Runner: `pytest` (detect `pytest.ini` / `[tool.pytest.ini_options]` / `tests/`); fallback `python3 -m unittest`.
- Invocation: `pytest -q` · fail-fast `pytest -x` · single node `pytest path::test_name`.
- **Caps** (avoid runaway): bound scope to the changed area (`pytest tests/<area>`) — do NOT run the whole suite on every micro-edit; use `--timeout=<n>` (pytest-timeout) where available; `-p no:cacheprovider` for hermetic runs.
- A test run that hangs past the cap = treat as failure, report, do not retry blindly.

## Naming  (PEP 8)
- `snake_case` functions/variables/modules · `PascalCase` classes · `UPPER_SNAKE` constants · leading `_` = non-public · `__dunder__` reserved.
- No single-letter names except short-lived loop indices / math (`i`, `x`).

## Hard style constraints
- PEP 8. Line length per repo config (`ruff`/`black` `line-length`, default 88) — read it, don't impose your own.
- Type hints on public signatures; `from __future__ import annotations` for forward refs on <3.10.
- `pathlib.Path` over `os.path`; f-strings over `%`/`.format`; context managers for resources.
- No bare `except:` (catch specific); no mutable default args; no `import *` in library code.
- Lint/type IF the repo configures them: `ruff check .` · `ruff format --check .` · `mypy <pkg>`. Match the repo's config; do not add tools the repo did not choose.

## Error-code & exit handling
- Libraries raise exceptions; CLIs map to exit codes via `sys.exit(int)` / `raise SystemExit(int)` — `0` success, non-zero failure.
- Do not swallow errors to force a green exit — surface the traceback.

## Verification alignment (this harness)
- `scripts/verification-gate.sh` runs `python3 -c "ast.parse(...)"` on changed `*.py` — **syntax only**. It does NOT run tests, lint, or types.
- ⇒ syntax-valid ≠ correct. After an edit, run the relevant `pytest` subset + `ruff`/`mypy` if configured, and report results — the gate's green is necessary, not sufficient.
