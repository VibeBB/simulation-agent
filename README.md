# simulation-agent

`sim` is an OpenHands plugin for deterministic, fail-closed engineering
simulation analysis. It complements circuit, mechanical, wire, UX, and bard
agents through versioned JSON files in the shared workspace; it does not import
sibling packages.

## Install

Install the `sim` plugin in OpenHands and make Docker available for the locked
solver image. The launcher uses Docker when an image reference resolves, or a
host Python environment when `SIM_LAUNCH_MODE=host` (or when automatic Docker
resolution is unavailable). Set `SIM_TOOLS_IMAGE` to select a tools image.
Run `/sim:doctor` to inspect solver availability.

## Commands

The plugin provides `/sim:doctor`, `/sim:run`, `/sim:spice`, `/sim:pdn`,
`/sim:thermal`, `/sim:wca`, `/sim:emc`, `/sim:dft`, `/sim:fem`, `/sim:rf`,
`/sim:gates`, `/sim:import`, and `/sim:respond`.

## Hooks

Session start runs `sim-doctor`, `intake-attachments`, and
`ensure-llm-profiles`. Attachment intake also runs on user prompts and
session stop. `inspect_image_with_vision` responses and `file_editor` image
views are recorded by post-tool hooks under `observations/sim/`; these records
are advisory evidence and never affect deterministic verdicts.

The JSON CLI is also available as `python -m sim`:

```bash
python -m sim doctor --warn
python -m sim validate examples/buck-regulator/buck.sim.json
python -m sim gates examples/buck-regulator/buck.sim.json
python -m sim respond examples/buck-regulator/buck.sim-request.json
```

CLI output is JSON. Exit status is 0 for `pass`, 1 for `fail`, 3 for
`unknown`, and 2 for usage or input errors. Generated artifacts are written
under `out/<name>/`: `sim-report.json`, `sim-report.md`, `manifest.json`,
`provenance.json`, and adapter output. These are projections of the brief and
must not be edited by hand.

## Analyses

| Analysis | Method |
| --- | --- |
| SPICE | Unmodified `ngspice` batch process; parse declared `.meas` results |
| PDN | DC nodal solve, copper temperature correction, IPC-2221 trace ampacity |
| Thermal | Scalar resistance paths or thermal nodal networks |
| WCA | Restricted expression AST; EVA, RSS, seeded Monte Carlo, bounded SPICE corners |
| EMC / ESD | Declared-data TVS, placement, critical-length, reference-plane, and decoupling rules |
| DFT | Test-point coverage, pad diameter, pitch, debug-header, and boundary-scan rules |
| FEM | CalculiX subprocess for a cantilever box plus an Euler–Bernoulli estimate |
| RF | Touchstone v1 band checks, optional KiCad-rfsim/openEMS subprocess, microstrip estimate |

Only deterministic analysis code emits verdicts. `fail` blocks acceptance;
`unknown` is unresolved and never becomes `pass` because a tool exited
successfully or an agent inferred a result. Analytic estimates are labelled and
do not replace unavailable solver output.

## Sibling cooperation

Simulation briefs (`*.sim.json`), imports (`*.connectivity.json`,
`*.envelope.json`, `*.contract.json`), and requests/responses (`*.sim-request.json`,
`*.sim-response.json`) are strict, versioned JSON contracts. Each imported file
is validated by local mirror models and recorded with its SHA-256 digest.
Declare consumed imports in the brief; every run rebuilds `imports.json` from
those validated declarations rather than trusting prior generated output.
Unsupported or malformed sibling content remains unknown; no sibling Python
package is imported.

## Development

Python 3.12+, uv `0.12.21`, and Docker are used by the repository workflow:

```bash
uv sync --locked
uv run python scripts/verify_all.py --stage fast
uv run python scripts/check_plugin_load.py
uv run python scripts/verify_all.py --stage standard
actionlint
docker build --target sim-tools -f docker/sim-tools.Dockerfile -t sim-tools:local .
uv run python scripts/smoke_image.py --image sim-tools:local
```

See [operations](docs/operations.md), [architecture](docs/architecture.md),
the [ADRs](docs/adr/), and [Docker notes](docker/README.md) for implementation
and deployment boundaries.
