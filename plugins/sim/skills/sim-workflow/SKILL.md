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
1. Run `sim doctor` and identify unavailable tools.
2. Gather source artifacts, explicit assumptions, operating conditions, and acceptance criteria.
3. Write a strict `*.sim.json` brief and validate it.
4. Run only the analyses supported by supplied evidence.
5. Review `sim-report.json`, `sim-report.md`, `provenance.json`, and `manifest.json`.
6. Treat every `unknown` as unresolved; never infer a pass from a clean process exit.

Generated files under `out/` are projections and are not hand-edited.
