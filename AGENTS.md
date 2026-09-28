# simulation-agent working agreement

`simulation-agent` is the deterministic engineering-analysis sibling of the
circuit, mechanical, wire, UX, and bard agents. Its brief schema in
`src/sim/brief.py` and import mirrors in `src/sim/imports.py` are contract
sources of truth.

## Invariants

- Python 3.12+, package `src/sim/`, uv `0.12.19`, hatchling, Pydantic v2, and
  MCP. Runtime dependencies are limited to `pydantic>=2` and `mcp>=1.29,<2`.
- All contracts are frozen and reject extra fields. Missing facts, tools,
  outputs, parse results, or acceptance bounds remain `unknown`.
- Only deterministic Python gates emit `pass`, `fail`, or `unknown`. Agent
  commentary is advisory and cannot promote a result.
- Inter-agent exchange is through validated JSON files in the shared workspace.
  Never import a sibling Python package.
- Keep paths inside the workspace; never log or commit secrets.
- `out/` files and `*.sim-response.json` files are generated artifacts and
  cannot be edited directly. Fix inputs and regenerate them.
- Copyleft solvers run as unmodified separate processes. Never link solver
  libraries or import-bind solver code.
- Code, docs, identifiers, and commit messages are in English.

## Layout

```text
src/sim/                 # schemas, deterministic checks, adapters, CLI, MCP
plugins/sim/              # OpenHands agents, commands, skills, hooks, launcher
tests/                    # contracts, analyses, adapters, plugin behavior
examples/buck-regulator/  # exercised multi-analysis example
docker/                   # sim-tools and optional sim-tools-em
scripts/                  # verification, docs, plugin-load, and smoke checks
docs/adr/                 # design decisions
```

Engineering guidance belongs in `plugins/sim/skills/`; the agents orchestrate
evidence gathering and the MCP server exposes deterministic entry points only.
Declare required hooks on each agent because plugin-level hooks do not
propagate to subagents.

## Verification

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
uv run python scripts/verify_all.py --stage fast
uv run python scripts/verify_all.py --stage standard
uv run python scripts/check_plugin_load.py
actionlint
```

Real-solver tests use the `tools` marker and skip only when the required
executable is absent. CI installs ngspice and CalculiX and therefore runs them.

## Git

Use focused commits with `feat(scope): summary` (72 characters maximum). Do
not amend, force-push, use `git add .`, skip hooks, or run destructive cleanup
commands. Keep the first research inventory unchanged.
