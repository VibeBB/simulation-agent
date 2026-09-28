---
name: sim-wca
description: Worst-case analysis methods, parameter tolerances, and reproducible sampling.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - worst-case analysis
  - WCA
  - tolerance stack
  - Monte Carlo
---
Use the declared nominal and absolute or percentage tolerance. For normal distributions, tolerance represents three standard deviations. EVA enumerates every vertex up to `max_vertices`; RSS uses central-difference sensitivities and tolerance deltas; MC uses `random.Random(seed)` and records the configured sample count. SPICE-measure outputs run one isolated ngspice process per corner/sample and honor `spice_mc_samples`. Cap overflow or any failed/missing measurement is unknown. Outputs without acceptance bounds are measured but remain unknown.
