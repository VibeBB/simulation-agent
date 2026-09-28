---
name: sim-fem-calculix
description: Cantilever finite-element modeling, CalculiX adapter boundaries, and analytic cross-checks.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - CalculiX
  - ccx
  - finite element
  - FEM
  - cantilever
---
The v0.1 geometry is a structured cantilever box under a tip force in −z. CalculiX is invoked as a separate process and its `.dat` output must provide displacement and integration-point stress. C3D20R applies the total tip force evenly to tip-face nodes. Euler–Bernoulli beam equations are an independent analytic estimate; they do not substitute for missing solver output. Cross-check is unknown for `L/h < 5`.
