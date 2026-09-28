---
name: sim-rf-openems
description: Touchstone, kicad-rfsim, openEMS, and analytic microstrip checks.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - RF
  - Touchstone
  - openEMS
  - kicad-rfsim
  - S-parameters
  - microstrip
---
Use a valid Touchstone v1 `.sNp` result or a kicad-rfsim JSON model. Each requested frequency band needs samples within its bounds and declared S11, S21, or VSWR limits. A non-passive result is unknown. The microstrip Hammerstad–Jensen calculation is a closed-form estimate independent of openEMS. Do not interpret an unavailable runner, missing data, or malformed Touchstone file as a pass.
