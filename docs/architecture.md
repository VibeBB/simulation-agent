# Architecture

The plugin separates authoritative computation from agent orchestration and
telemetry.

## L1 — deterministic core

`brief.py` validates versioned engineering inputs. `imports.py` validates local
mirrors of sibling JSON contracts and hashes their source bytes. `analysis.py`
implements the declared numerical methods, while solver adapters invoke
ngspice, CalculiX, and optional KiCad-rfsim as unmodified subprocesses.
`gates.py` aggregates checks fail-first: any `fail` yields `fail`; otherwise
any `unknown` (or no checks) yields `unknown`; only a non-empty all-pass set
yields `pass`.

## L2 — agent surface

The OpenHands `sim` plugin contains three agents, 13 commands, and 10
engineering skills. Agents gather explicit evidence, author briefs, and
interpret generated reports; they do not compute or author verdicts. Plugin
hooks protect generated files and summarize unresolved checks. The launcher
defaults to a locked Docker image; host execution requires an explicit mode,
while `auto` preserves Docker-when-available behavior. The low-level MCP
server and JSON CLI call the same core entry points.

## L3 — telemetry and reports

`run.py` executes imports, analyses, and adapters; `report.py` writes
`sim-report.json`, `sim-report.md`, `manifest.json`, and `provenance.json`.
Provenance records the brief hash, imported-file hashes, tool versions, and UTC
generation time. `unknown` is blocking and must be resolved from source
evidence, not conversational inference.

```text
*.sim.json → strict validation → local JSON imports → analysis/adapters
           → gate aggregation → reports + provenance + artifact manifest
*.sim-request.json ───────────────────────────────────────────────┘
           → needs_info / accepted / rejected response with report hash
```

## Security boundary

All user-supplied paths are confined to `OPENHANDS_PROJECT_DIR` (or the
current working directory); paths that traverse symlinks are rejected.
Copyleft solvers and the optional openEMS stack
are never imported into the Python process. Docker runs without network access,
mounts the project workspace, and forwards only explicit solver configuration
variables. Generated output is protected from direct agent edits.
