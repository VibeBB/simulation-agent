---
name: sim-brief-rules
description: Path rule — schema and provenance reminders injected whenever a *.sim.json or *.sim-request.json file is touched.
version: 0.1.0
license: BSD-3-Clause
paths:
  - "**/*.sim.json"
  - "**/*.sim-request.json"
---

# Sim brief file rules

- `*.sim.json` follows the `SimulationBrief` schema in `src/sim/brief.py`
  (in plugin-only installs, run `sim schema` for the exact JSON Schema).
  Unknown fields, non-finite numbers, and unsupported values are errors;
  at least one analysis section is required.
- `*.sim-request.json` is the sister-facing request contract (`from_system`
  `circuit`/`mech`/`wire`/`bard`); requests are validated just as strictly
  and produce generated `*.sim-response.json` files that are never
  hand-edited.
- Do not guess geometry, operating points, material properties, ratings, or
  acceptance bounds — missing evidence stays `unknown`. Declared imports
  (`*.connectivity.json`, `*.envelope.json`, `*.contract.json`) are
  re-validated by strict mirrors with SHA-256 pinning on every run.
- Pass/fail/unknown verdicts come only from deterministic gates; a brief
  that parses is not evidence of a passing analysis.

```json
{
  "schema_version": 1,
  "name": "brief-rules",
  "emc": {}
}
```
