---
name: sim-spice
description: SPICE and tolerance-analysis workflow, measurements, and solver failure handling.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - ngspice
  - SPICE
  - circuit transient
  - WCA
---
Provide a reviewed netlist or explicit element model, analyses, `.meas` outputs, operating conditions, and limits. Supported one-line analyses and measures are taken from the brief; source-declared analyses and measures are replaced. `.control` blocks are not supported. `ngspice` runs as an unmodified batch subprocess. Parse errors, timeouts, missing measurements, and missing binaries are `unknown`. Tolerance analysis evaluates declared bounds only; do not alter the authored deck or thresholds.
