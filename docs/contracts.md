# Contracts

Every cross-boundary JSON is a frozen Pydantic v2 model: unknown fields are
rejected, missing data becomes `unknown`, and nothing is silently coerced.
All paths must resolve inside the workspace (`workspace.py`).

## `*.sim.json` — simulation brief (schema_version 1)

`SimulationBrief`: `schema_version`, `name` (slug-ish, `[A-Za-z0-9_-]+`),
`description`, `imports[]` (`ImportRef` path+system+sha256), and at least
one analysis section:

- `spice`: `SpiceSection` — `deck` (`netlist_path` xor `elements[]`,
  `models[]`, `analyses[]`, `timeout_s`), `measures[]` (name + one-line
  `.meas` statement + optional `min`/`max`), `corners[]` for bounded WCA
  reruns.
- `pdn`: `PdnSection` — `rails[]` of `PdnRail` (`PdnBranch`, `PdnLoad`)
  for DC drop and IPC-2221 ampacity checks.
- `thermal`: `ThermalSection` — scalar `paths[]` (`ThermalPath`) or
  `networks[]` (`ThermalNetwork` of `ThermalComponent`/`ThermalResistance`).
- `wca`: `WcaSection` — `parameters[]` and `outputs[]` with `nominal`,
  tolerance, and method (`eva|rss|monte_carlo`) plus seed/samples.
- `emc`: `EmcSection` — `interfaces`, `protection` (TVS `EmcProtection`),
  `devices`, `signals`, `decoupling` (`Decap`) rules.
- `dft`: `DftSection` — `nets`, `required`, `test_points[]` (`TestPoint`
  ref/net/pad_diameter_mm/x_mm/y_mm/side), `min_coverage`,
  `min_pad_diameter_mm`, `min_pitch_mm`, `debug_header`, BGA/boundary-scan.
- `fem`: `FemSection` — cantilever `geometry` (`FemGeometry`),
  `material` (`FemMaterial`), `load` (`FemLoad`), `mesh` (`FemMesh`),
  `limits` (`FemLimits`).
- `rf`: `RfSection` — `bands` (`RfBand` frequency span + S-parameter
  limits), optional `rfsim` (`RfSim`) and `microstrip` (`Microstrip`).
- `ruggedness`: `RuggednessSection` — at least one of `vibration`, `drop`,
  `ingress`. `vibration` (`psd_g2_hz`, optional `q` (default √fn) and
  `min_fn_hz`, `parts[]` of `RuggedPart` ref/x_mm/y_mm (board-centred)/
  length_mm/parallel_to/steinberg_c) needs `plate` (`RuggedPlate`
  width/depth/thickness, `youngs_mpa`, `poisson`, `density_kg_m3`,
  `component_mass_g`). Checks: simply supported plate first mode
  (`ruggedness.vibration.fn` when `min_fn_hz` is set) and, per part, Miles'
  3σ displacement against Steinberg's allowable
  `0.00022·B/(c·h·r·√L)` (r = |cos(πx/a)·cos(πy/b)|). `drop`
  (`height_mm`, `pulse_ms`, `restitution` 0–1, `max_shock_g`): half-sine
  peak `π(1+e)√(2gh)/(2τ)`. `ingress` (`code` `IP[0-6X][0-9X]`,
  `openings_min_mm[]`, `sealed`): first digits 1–4 need every opening below
  the 50/12.5/2.5/1.0 mm probe; dust digits 5/6 and any water digit are
  `unknown` (IEC 60529 test required), and a water digit with unsealed
  openings is `fail`.
- `lifetime`: `LifetimeSection` — `model` `arrhenius`, `parts[]` of
  `LifetimePart` (`ref`, `rated_life_h` at `rated_temp_c`, explicit
  `activation_energy_ev`, `profile[]` of `LifetimeStress`
  `temperature_c`/`fraction` summing to 1, `required_life_h`, `source`).
  Each step lives `L_rated·exp(Ea/k·(1/T − 1/T_rated))` (k = 8.617333262e-5
  eV/K, temperatures in K) and steps combine by Miner's rule. Check
  `lifetime.<ref>.life_h` passes when the life meets `required_life_h`; an
  out-of-range factor is `unknown`. A failing check's detail carries the
  margin, the life-doubling temperature step, the uniform profile cooling
  and the rated life that would meet the requirement. No activation energy
  or 10 °C rule is assumed.

## Sister imports

`imports[]` entries reference files mirrored by `src/sim/imports.py` models
(`WireContract`, `ConnectivitySource`, `EnvelopeSource`, `ContractElementSource`,
`ContractImportedSource`, …). Each import is bound to the source file's
sha256 in `imports.json` written by `write_import_record`.

## `*.sim-request.json` — v1 sister request (schema_version 1)

`SimulationRequest`: `schema_version`, `from_system` (circuit, mech, wire,
bard, firmware, fpga, prodeng, dashboard, doc, ux), `request_id`, `kind`
(analysis or `any`), `brief_path`, `question`, optional `requested_by`.

## `*.sim-response.json` — v1 answer (schema_version 2)

`SimulationResponse`: `schema_version` 2, `request_id`, `status`
(`accepted|rejected|needs_info`), optional `verdict`, `report_path`,
`request_sha256`, `brief_sha256`, optional `decision_refs` (validated
against `valid_event_ids`), `reasons[]`. Written atomically by
`write_response`.

## `sim-report.json` — analysis report (schema_version 2)

`SimulationReport`: `schema_version` 2, `name`, `verdict`, `checks[]`
(id, verdict, detail), `measures[]`, `files[]`, `plots[]` (`PlotInfo`:
path + sha256 + kind), `plot_errors[]`. `sim-report.md` is the human
projection with a Plots section; `manifest.json`/`provenance.json` bind
inputs to outputs.

## `liaison/*.ux-request.json` / `*.ux-response.json` — SLP v2

`UXRequest` (schema_version 2, all fields required): `system` ux-creator,
`id`, `target_agent`, `stage`, `risk` (high risk must cite a `UX-JOB-\d+`
in `rationale`), `purpose`, `rationale`, `requested_changes[]`, `inputs[]`
(path+sha256), `expected_deliverables[]`, `acceptance[]`, `depends_on[]`,
`created_at`. `UXResponse`: `request`, `responder`, `status`
(`done|in_progress|needs_info|rejected`…), `reason`, `gate_verdicts[]`,
`artifacts[]` (path+sha256), `reports[]`, `decision_refs[]`,
`impression_refs[]`, `questions[]`.

## VRP v1 records — `observations/sim/*.jsonl`

Envelope: `schema_version` 1, `kind`, `plugin` sim, `sequence`,
`event_id` (sha256 over `{kind, sequence, body}`), `recorded_at`
(tz-aware ISO-8601). Kinds: `decision` (DecisionRecord — id, stage,
question, principles, options, chosen, rationale, evidence, assumptions,
unknowns, risks, revisit_when, decided_by), `stage_impression` (stage,
artifacts[], impression ≥400 chars/≥3 sentences), `vision_review`
(image_path+sha256 or source_event_id, model, checklist slug, findings[],
impression). `valid_event_ids` re-validates every line and recomputes the
event_id, matching the Stop-hook mirror (`_records.record_errors`).
