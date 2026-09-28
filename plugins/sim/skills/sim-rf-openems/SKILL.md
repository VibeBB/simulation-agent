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
## RF field reference

| Field | Meaning and units |
| --- | --- |
| `touchstone_path` | Workspace-relative v1 `.sNp` measurement/simulation result; mutually exclusive with `rfsim`. |
| `rfsim` | `model_path` to kicad-rfsim JSON, optional `runner_path`, and `timeout_s` (seconds, default 3600). |
| `microstrip[]` | `name`, `width_mm`, `height_mm`, `thickness_um` (default 35), substrate `er`, `target_ohm`, and `tol_pct` (default 10%). |
| `bands[]` | `name`, `f_min_hz`, `f_max_hz`, optional `s11_max_db`, `s21_min_db`, and `vswr_max`. |

```json
{
  "schema_version": 1,
  "name": "rf-reference",
  "rf": {
    "touchstone_path": "measurements/device.s2p",
    "bands": [
      {
        "name": "wifi",
        "f_min_hz": 2400000000.0,
        "f_max_hz": 2500000000.0,
        "s11_max_db": -10.0,
        "s21_min_db": -3.0,
        "vswr_max": 2.0
      }
    ],
    "microstrip": [
      {
        "name": "feed",
        "width_mm": 1.2,
        "height_mm": 0.8,
        "thickness_um": 35.0,
        "er": 4.2,
        "target_ohm": 50.0,
        "tol_pct": 10.0
      }
    ]
  }
}
```

## Gates, formulas, and assumptions

Gate IDs include `rf.band.<name>.s11_maximum`, `.s21_minimum`, `.vswr_maximum`, `rf.microstrip.<name>`, `rf.touchstone`, and `rf.rfsim`. Each band needs in-band samples and at least one limit. A non-passive result, missing sample, missing measurement, malformed file, or unavailable runner yields `unknown`; a measured limit violation is `fail`.

The Touchstone v1 passivity screen examines every frequency: any `|Sᵢⱼ| > 1 + 10⁻⁶`, or any driven-port column with `Σᵢ|Sᵢⱼ|² > 1.001`, marks the dataset non-passive. It is a conservative column-power screen rather than a full multiport passivity proof.

Microstrip impedance uses a quasi-static Hammerstad–Jensen-style estimate with normalized width `u = w/h`, copper thickness correction `u_eff`, and effective permittivity `ε_eff = (εr+1)/2 + (εr−1)/(2√(1+12/u_eff))`. For `u_eff ≤ 1`, `Z₀ = 60/√ε_eff · ln(8/u_eff + u_eff/4)`; otherwise `Z₀ = 120π/[√ε_eff(u_eff+1.393+0.667 ln(u_eff+1.444))]`. Inputs are mm/μm and unitless εr; results are Ω. It omits dispersion, solder mask, roughness, and 3D field effects.

The pinned openEMS-Project v0.37.0-rc1 source is commit `92b82520054a62201ac69bd905fdf2533810367f`. Upstream warns that kicad-rfsim CPW and stripline ports on this release candidate report impedance 20–50% low. Treat those geometries as unvalidated even when S-parameters appear passive; require a better solver/measurement or explicitly report the limitation.

## Pitfalls

- Passivity is necessary, not sufficient: passing it does not prove a model, port, or geometry is correct.
- `S21` needs at least two ports; in-band sample coverage must be present.
- Do not turn missing bands, unavailable openEMS/runner, or malformed Touchstone data into a pass.
- The microstrip estimate is not an openEMS result and does not validate CPW/stripline geometry.
