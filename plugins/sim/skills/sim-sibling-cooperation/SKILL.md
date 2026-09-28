---
name: sim-sibling-cooperation
description: Exchange typed simulation requests, imports, and responses with sibling agents.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - simulation request
  - simulation response
  - import circuit
  - import wire contract
---
## Inbound contracts

All imports are strict schema version 1 and unknown fields are rejected. `sim import <file> --brief <brief>` validates a file, records its SHA-256, source system, and extracted fields. To use it during a run, declare `{ "path": "...", "system": "circuit|mech|wire|bard" }` in the brief's `imports`; each run revalidates the declaration and rebuilds `imports.json`.

| File suffix | Required structure and fields consumed |
| --- | --- |
| `*.connectivity.json` | Top-level `schema_version`, `system` (`circuit`, `csv`, `kbl`, or `vec`), `connectors`, `nets`. Connectors use `ref`, `cavities[]`, optional `family_hint`, `housing`, `rated_current_a` (A, default 3), `rated_voltage_v` (V, default 250). Nets use `ref`, `signal_class` (`power`, `ground`, `signal`, `analog`, `data`, `highspeed`, `shield`), `voltage_v` (V), `current_a` (A). There is no connector-to-net mapping. |
| `*.envelope.json` | Top-level `schema_version`, `system: "mech"`, and non-empty `anchors[]`; each anchor has `name`, optional `kind` (`clip`, `grommet`, `breakout`, `other`), and optional 3D `position_mm`. |
| `*.contract.json` | Strict wire-contract fields: `contract_id`, `name`, `revision`, `connectors`, `wire_types`, `nets`, `wires`, optional `routes`, `splices`, `segregations`, `service`, `imported_sources`, `ipc_class`, and `ambient_temperature_c`. Each extracted wire uses `id`, `net` (an `N#` net ID), `wire_type` (a `WT#` ID), `length_m`, `from_endpoint`, and `to_endpoint`; its referenced wire type supplies `resistance_ohm_per_km` and `ampacity_a`. Extracted nets use `id`, optional `ref`, `signal_class`, `voltage_v`, and `current_a`. Required wire-type fields also include `name`, `gauge_mm2`, `outer_diameter_mm`, `reference_temp_c`, `insulation_rating_v`, `insulation_temp_c`, and `min_bend_factor`; connector/cavity endpoints and cross-references are validated. |
| `*.sim-request.json` | `schema_version: 1`, `from_system`, `request_id`, `kind`, `brief_path`, `question`, optional `requested_by`. `kind` is `spice`, `pdn`, `thermal`, `wca`, `emc`, `dft`, `fem`, `rf`, or `any`. |

The connectivity schema's `connectors[]` and `nets[]` are separate lists; never infer connector nets from list order, cavity count, or imported net classes. An undeclared imported connector yields `unknown` `emc.interface.<ref>` until its nets are explicitly declared. Imports have no standalone passing analysis gate; a failed import declaration produces `imports.<system>.<filename>` with `unknown`.

## Request and response

`sim respond <request.sim-request.json>` reads the request's `brief_path`, runs the requested section, and writes `<stem>.sim-response.json` beside the request. A v1 response has `schema_version`, `request_id`, `status` (`accepted`, `rejected`, `deferred`, `needs_info`), optional `verdict` (`pass`, `fail`, `unknown`), paired optional `report_path` and lowercase 64-hex `sha256`, and `reasons[]`. Accepted requires a hashed report and `verdict: "pass"`; rejected requires a hashed report and `verdict: "fail"`. Missing evidence maps to `needs_info`.

Example request and response payloads:

```text
request:
{"schema_version":1,"from_system":"circuit","request_id":"REQ-17","kind":"pdn","brief_path":"board.sim.json","question":"Does VDD meet its declared drop limit?","requested_by":"circuit-agent"}
response:
{"schema_version":1,"request_id":"REQ-17","status":"needs_info","verdict":"unknown","reasons":["solver evidence unavailable"]}
```

Brief import example:

```json
{
  "schema_version": 1,
  "name": "sibling-reference",
  "imports": [{"path": "board.connectivity.json", "system": "circuit"}],
  "emc": {}
}
```

## Pitfalls

- Preserve source paths and hashes; do not hand-edit generated `imports.json` or response files.
- Do not treat imported current/voltage as a connector pin assignment.
- `accepted` is only for a deterministic pass; `rejected` is only for a deterministic fail; `unknown` requires `needs_info`.
