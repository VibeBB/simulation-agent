---
name: sim-emc-esd
description: EMC, ESD, high-speed, and decoupling rule checks.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - EMC
  - ESD
  - IEC 61000-4-2
  - decoupling
  - reference plane
---
Declare each interface, external net, IEC 61000-4-2 level, protection device, protected-device absolute maximum, trace timing/length, reference-plane continuity, and decoupling placement. Missing v_max, abs_max, rise time, or other required data produces unknown. Rule checks are deterministic screening checks, not conducted/radiated emissions or immunity simulation.
