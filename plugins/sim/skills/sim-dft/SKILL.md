---
name: sim-dft
description: Test-point coverage, pad and pitch, debug header, and boundary-scan gates.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - design for test
  - DFT
  - test point
  - boundary scan
  - JTAG
  - SWD
---
Declare required nets explicitly or import normalized connectivity, then identify every test point's net, pad size, position, and side. Coverage must meet `min_coverage`; same-side points are checked pairwise for `min_pitch_mm`. A required debug header must be SWD/JTAG/UART rather than `none`. Every listed BGA ref requires a declared boundary-scan chain. Empty required-net evidence is unknown.
