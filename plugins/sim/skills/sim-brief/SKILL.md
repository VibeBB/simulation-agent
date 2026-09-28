---
name: sim-brief
description: Simulation brief schema, required evidence, and fail-closed input rules.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - simulation brief
  - simulation schema
  - analysis limits
---
Use `sim schema` as the v0.1 machine-readable contract. Brief files end in `*.sim.json`. Unknown keys are errors. Do not add assumed dimensions, nominal values, solver options, thermal paths, or acceptance limits. Keep file paths workspace-relative and provide an explicit threshold for every output that must be judged.

The schema is versioned; unsupported features must be reported as missing information, not approximated.
