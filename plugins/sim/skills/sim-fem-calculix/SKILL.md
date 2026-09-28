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
## FEM field reference

| Field | Meaning and units |
| --- | --- |
| `geometry` | `kind: cantilever_box`; `length_mm`, `width_mm`, and `height_mm` (mm). |
| `material` | `name`, `youngs_mpa` (MPa), `poisson` (unitless), `yield_mpa` (MPa), optional `density_kg_m3`. |
| `load` | `kind: tip_force`, positive `force_n` (N), and `direction: "-z"`. |
| `mesh` | Positive cell counts `nx`, `ny`, `nz`; `element` is `C3D8I` or `C3D20R`. |
| `limits` | `min_safety_factor` (default 2) and optional `max_deflection_mm` (mm). |
| `cross_check_tolerance` | Maximum relative FEM/beam deflection difference; defaults to `0.15` (15%). |
| `timeout_s` | CalculiX subprocess timeout in seconds; defaults to 300. |

```json
{
  "schema_version": 1,
  "name": "cantilever-reference",
  "fem": {
    "geometry": {
      "kind": "cantilever_box",
      "length_mm": 100.0,
      "width_mm": 25.0,
      "height_mm": 10.0
    },
    "material": {
      "name": "aluminum",
      "youngs_mpa": 69000.0,
      "poisson": 0.33,
      "yield_mpa": 276.0
    },
    "load": {"kind": "tip_force", "force_n": 10.0, "direction": "-z"},
    "mesh": {"nx": 2, "ny": 1, "nz": 1, "element": "C3D8I"},
    "limits": {"min_safety_factor": 2.0, "max_deflection_mm": 1.0},
    "cross_check_tolerance": 0.15
  }
}
```

## Gates, equations, and assumptions

`fem.safety_factor` uses parsed CalculiX integration-point stress; `fem.deflection` compares maximum absolute z displacement with `max_deflection_mm` when that limit is supplied; `fem.cross_check` compares the mean tip-face z displacement with beam theory; `fem.analytic.safety_factor` is the independent analytic result. `pass` meets the configured limit, `fail` violates it, and `unknown` means ccx failed, required `.dat` output is absent/unparseable, or the geometry is outside the cross-check rule (`L/h < 5`).

For a rectangular Euler–Bernoulli cantilever with tip load `F`, span `L`, width `b`, height `h`, and elastic modulus `E`, `I = b h³/12`, `δ_tip = F L³/(3 E I)`, `σ_max = 6 F L/(b h²)`, and safety factor is yield stress divided by bending stress. Convert dimensions consistently: input geometry is mm, force N, and modulus/yield MPa. The model assumes linear elasticity, small deflection, a prismatic beam, and a static force.

The generated structured hex mesh uses CalculiX as an unmodified subprocess. `C3D20R` and `C3D8I` are supported; total force is distributed uniformly over tip-face nodes. The deflection limit uses maximum nodal displacement, while the beam comparison uses the tip-face mean to approximate centroid translation.

## Pitfalls

- A valid input deck is not evidence of solver success; preserve and parse real `.dat` output.
- Do not mix N/mm/MPa with SI units in hand calculations.
- Coarse meshes, shear deformation, support constraints, and local face-node extrema can shift FEM results from beam theory.
- An analytic estimate never replaces missing CalculiX evidence.
