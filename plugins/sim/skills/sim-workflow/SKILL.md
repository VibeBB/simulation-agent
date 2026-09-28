---
name: sim-workflow
description: Safe end-to-end workflow for deterministic simulation brief authoring and gates.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - simulation brief
  - run simulation
  - simulation report
---
## End-to-end flow

1. Run `/sim:doctor`; use strict mode when a solver is required for acceptance. Record missing tools before choosing analyses.
2. Gather source artifacts, operating conditions, material/geometry facts, and explicit limits. Use `/sim:import <file> --brief <brief>` for supported sibling contracts; add the same path and system to `imports[]`.
3. Author a workspace-relative `*.sim.json` brief using only supported evidence. Validate with `sim validate <brief>` or inspect the model using `sim schema`/the `sim_schema` MCP tool.
4. Execute `/sim:run <brief>` for every declared section or one focused command (`/sim:spice`, `/sim:pdn`, `/sim:thermal`, `/sim:wca`, `/sim:emc`, `/sim:dft`, `/sim:fem`, `/sim:rf`).
5. Use `/sim:gates <brief>` for the complete gate summary. Review `out/<name>/sim-report.json`, `sim-report.md`, `provenance.json`, and `manifest.json`; cite gate IDs, measurements, tools, and source hashes.
6. For a sibling request, run `/sim:respond <request.sim-request.json>` and return the generated response path. A deterministic `pass` is `accepted`, `fail` is `rejected`, and `unknown` or missing evidence is `needs_info`.

The OpenHands command set is `/sim:doctor`, `/sim:run`, `/sim:gates`, `/sim:import`, `/sim:respond`, `/sim:spice`, `/sim:pdn`, `/sim:thermal`, `/sim:wca`, `/sim:emc`, `/sim:dft`, `/sim:fem`, and `/sim:rf`. Commands use the installed plugin launcher; the equivalent source-tree form is `python3 plugins/sim/scripts/sim_launcher.py <subcommand> ...`.

```json
{
  "schema_version": 1,
  "name": "workflow-reference",
  "dft": {
    "nets": ["VIN"],
    "required": "all",
    "test_points": [
      {
        "ref": "TP1",
        "net": "VIN",
        "pad_diameter_mm": 1.0,
        "x_mm": 10.0,
        "y_mm": 5.0,
        "side": "top"
      }
    ],
    "require_debug_header": false
  }
}
```

## Gate semantics and pitfalls

The top-level `schema_version` is `1`; `name` identifies report outputs; `description` is context; `imports` list strict `{path, system}` records; analysis objects are `spice`, `pdn`, `thermal`, `wca`, `emc`, `dft`, `fem`, and `rf`. Each analysis skill defines its fields and units. A brief must contain at least one section.

Across all analyses, `pass` means the implemented deterministic predicate meets the declared criterion, `fail` means it violates a criterion, and `unknown` means required facts, solver evidence, supported input, or an acceptance bound is missing. A clean exit or plausible narrative cannot promote unknown to pass.

- Do not edit generated `out/` files; rerun from validated inputs.
- Keep solver availability and model assumptions visible in the report.
- Never invent acceptance criteria to silence a failing or unknown gate.
- Treat the analytic PDN, thermal, EMC, DFT, WCA, and microstrip checks as models/rules—not a substitute for physical qualification.
