---
name: sim-pdn-thermal
description: Power-integrity and thermal network modeling, assumptions, and gate boundaries.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - power integrity
  - PDN
  - thermal resistance
---
PDN inputs require explicit source voltage, node/branch topology, trace or plane dimensions, copper thickness, temperature, load currents, and voltage-drop limits. Trace ampacity uses IPC-2221 as a rule estimate, not an electrothermal solver. Imported wire branches and currents must resolve from a validated wire/connectivity contract. Floating or singular networks are unknown.

Thermal checks use either a complete scalar path (`theta_ja_c_per_w` or the `theta_jc`/`theta_cs`/`theta_sa` series) or a declared resistance network referenced to an ambient node. Missing resistances, unresolved power nodes, non-finite values, and singular networks are unknown.
