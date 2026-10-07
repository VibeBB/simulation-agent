# Architecture

`sim` is a fail-closed, deterministic engineering-analysis plugin. It is
organized in three layers:

- **L1 — contracts and workspace.** Frozen Pydantic v2 models (extra fields
  rejected) define every JSON that crosses a boundary: the `*.sim.json` brief,
  sister-contract imports, `*.sim-request.json` / `*.sim-response.json`,
  SLP v2 `*.ux-request.json` / `*.ux-response.json`, `sim-report.json`, and the
  VRP v1 record lines. `workspace.py` confines every path to the workspace.
- **L2 — deterministic analysis and rendering.** `analysis.py` computes
  first-order checks; `adapters/` run unmodified copyleft solvers as
  subprocesses and parse their output; `gates.py` turns check data into
  `pass`/`fail`/`unknown`; `plot.py` renders deterministic PNGs with no
  third-party dependency; `records.py` and `liaison.py` validate and append
  records and responses.
- **L3 — surfaces.** `cli.py` (`python -m sim`), `mcp_server.py` (MCP tools
  with inline PNG images), `run.py`/`report.py` (orchestration and report
  emission), `doctor.py`/`tools.py` (tool discovery), and the plugin shell
  (`plugins/sim/` agents, commands, skills, hooks, launcher). The launcher
  re-executes the CLI inside the pinned `sim-tools` Docker image; it is
  Docker-only (ADR-0008).

Missing facts, tools, outputs, or parse results produce `unknown` — never a
pass. Agent commentary and vision reviews are advisory: only L2 gates emit
verdicts.

## Module map

Every public function and class of `src/sim` (generated from the AST):

### `src/sim/analysis.py` — deterministic analysis bodies
`branch_resistance`, `run_pdn_rail`, `run_thermal`, `run_wca`, `run_emc`,
`run_dft`, `run_fem_analytic`, `run_ruggedness` (`plate_natural_frequency`,
`drop_peak_g`, `plate_fn_guidance`, `drop_guidance`), `thermal_guidance`,
`run_lifetime` (`arrhenius_life_h`, `lifetime_guidance`), `run_bounds`,
`microstrip_impedance`

### `src/sim/brief.py` — `*.sim.json` schema
`Model`, `ImportRef`, `SpiceElement`, `Measure`, `SpiceDeck`, `SpiceSection`,
`PdnLoad`, `PdnBranch`, `PdnRail`, `PdnSection`, `ThermalPath`,
`ThermalComponent`, `ThermalResistance`, `ThermalNetwork`, `ThermalSection`,
`WcaParameter`, `WcaOutput`, `WcaSection`, `EmcInterface`, `EmcProtection`,
`EmcDevice`, `EmcSignal`, `Decap`, `Decoupling`, `EmcSection`, `TestPoint`,
`DebugHeader`, `DftSection`, `FemGeometry`, `FemMaterial`, `FemLoad`,
`FemMesh`, `FemLimits`, `FemSection`, `RfBand`, `Microstrip`, `RfSim`,
`RfSection`, `SimulationBrief`, `load_brief`, `schema`

### `src/sim/cli.py` — `python -m sim` entry point
`JsonArgumentParser`, `main`

### `src/sim/doctor.py` — tool availability report
`run_doctor`

### `src/sim/expr.py` — restricted arithmetic expression evaluator (WCA)
`evaluate`

### `src/sim/gates.py` — verdict machinery
`GateCheckData`, `GateCheck`, `GateReport`, `check`, `aggregate`

### `src/sim/imports.py` — sister-contract import mirrors
`StrictModel`, `ContractElementSource`, `ContractTemperaturePoint`,
`ConnectorSource`, `NetSource`, `ConnectivitySource`, `EnvelopeAnchor`,
`EnvelopeSource`, `ContractWireType`, `ContractCavity`, `ContractConnector`,
`ContractNet`, `Endpoint`, `ContractSplice`, `ContractWire`,
`ContractSegment`, `ContractRoute`, `ContractSegregation`, `ContractService`,
`ContractImportedSource`, `WireContract`, `import_source`,
`write_import_record`

### `src/sim/liaison.py` — SLP v2 UX-creator liaison
`InputRef`, `ArtifactRef`, `GateVerdict`, `UXRequest`, `UXResponse`,
`liaison_dir`, `request_path`, `response_path`, `load_request`, `event_ids`,
`ux_respond`, `inbox`

### `src/sim/linalg.py` — tiny dense linear solver (PDN/thermal networks)
`solve`

### `src/sim/mcp_server.py` — MCP stdio server
`tool_specs`, `dispatch_tool`, `main`

### `src/sim/plot.py` — deterministic PNG plotting (stdlib only)
`fmt`, `Canvas`, `line_chart`, `parse_limit`, `margin_chart`,
`stacked_bar_chart`, `scatter_board`

### `src/sim/records.py` — VRP v1 record protocol
`sentence_count`, `impression_is_prose`, `sha256_file`, `tree_sha256`,
`ArtifactRef`, `EvidenceRef`, `DecisionOption`, `EvidenceInput`,
`DecisionInput`, `StageImpressionInput`, `VisionReviewInput`,
`DecisionRecord`, `StageImpression`, `VisionReview`, `records_dir`,
`record_decision`, `record_impression`, `record_vision_review`,
`valid_event_ids`, `records_summary`

### `src/sim/report.py` — `sim-report` projection
`PlotInfo`, `SimulationReport`, `sha256_file`, `render_markdown`,
`write_outputs`

### `src/sim/requests.py` — `*.sim-request.json` schema
`SimulationRequest`, `load_request`

### `src/sim/responses.py` — `*.sim-response.json` writer (schema v2)
`SimulationResponse`, `write_response`

### `src/sim/run.py` — brief → analyses → report orchestration
`run_simulation`

### `src/sim/tools.py` — executable discovery
`ToolInfo`, `DetailedToolInfo`, `discover_tools`

### `src/sim/touchstone.py` — Touchstone v1 parser (RF)
`TouchstoneSample`, `TouchstoneData`, `parse`

### `src/sim/workspace.py` — workspace confinement
`workspace_root`, `workspace_path`, `reject_symlinks`

### `src/sim/adapters/` — solver subprocess adapters
- `calculix.py`: `generate_input`, `parse_dat`, `run_calculix`
- `ngspice.py`: `render_deck`, `parse_measures`, `run_ngspice`
- `spice_raw.py`: `RawPlot`, `parse_raw`, `parse_raw_bytes`

## Data flow

`brief → load_brief → imports merge → run_simulation → adapter/analysis →
GateReport → write_outputs (sim-report.json v2 + .md + manifest + plots)`.
CLI and MCP dispatch reach the same entry points; MCP image tools
additionally return up to `MAX_PLOT_IMAGES` (8) sha256-verified PNGs inline.
Liaison and responses consume the same workspace contracts, and every
decision/impression/vision-review line is appended through `records.py`
after full re-validation.
