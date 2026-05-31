# Per-stack operational rules

Stack-specific operational rules live here as `<stack>.md` (e.g. `dotnet.md`, `node.md`, `python.md`): entry-point search heuristics, build / test commands, naming conventions, hard style constraints, and test-execution caps for that stack.

Agents read them by inferring the stack from the prompt:

- `agents/developer.md` reads the matching file before writing code (build commands, naming, iteration caps).
- `agents/analyzer.md` reads it before investigation (entry points, schema hints, build-flag detection).

If no file exists for the inferred stack, agents **escalate rather than invent** stack rules.

This directory ships empty by design — add your own `<stack>.md` files as needed. Tracked as N1 in `ROADMAP.md`.
