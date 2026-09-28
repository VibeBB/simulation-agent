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
## DFT field reference

| Field | Meaning and units |
| --- | --- |
| `nets`, `critical_nets` | Explicit net names. `required` selects `all`, `power_and_critical`, or `listed`; listed mode uses `critical_nets` when non-empty, otherwise `nets`. |
| `test_points[]` | Each point has `ref`, `net`, `pad_diameter_mm` (mm), `x_mm`/`y_mm` (mm), and `side` (`top` or `bottom`). |
| `min_coverage` | Required fraction in `[0,1]`; defaults to `1.0`. |
| `min_pad_diameter_mm` | Minimum probe pad diameter, mm; defaults to `0.9`. |
| `min_pitch_mm` | Minimum same-side point spacing, mm; defaults to `2.54`. |
| `debug_header` | `{kind, ref}`; `kind` is `swd`, `jtag`, `uart`, or `none`. |
| `require_debug_header` | Whether a non-`none` debug header is required; defaults to `true`. |
| `bga_refs`, `boundary_scan_chain` | BGA refs and whether a chain is explicitly declared. |

```json
{
  "schema_version": 1,
  "name": "dft-reference",
  "dft": {
    "nets": ["GND"],
    "required": "all",
    "test_points": [
      {
        "ref": "TP1",
        "net": "GND",
        "pad_diameter_mm": 1.0,
        "x_mm": 0.0,
        "y_mm": 0.0,
        "side": "top"
      }
    ],
    "require_debug_header": false
  }
}
```

## Gates and assumptions

`dft.coverage` measures covered required nets against `min_coverage`; `dft.pad_size` checks every declared pad; `dft.pitch` checks pairwise same-side spacing; `dft.debug_header` enforces the required header; `dft.boundary_scan` is emitted when `bga_refs` is non-empty. `pass` meets the declared rule, `fail` violates it, and `unknown` means the evidence is insufficient (for example, no required nets or fewer than two points for pitch).

Coverage is a set-membership calculation, not a probe-access or manufacturing simulation. Position is planar board position in mm; points on opposite sides are not compared for pitch.

## Pitfalls

- Do not infer critical nets, test-point connections, BGA chain coverage, or board side.
- Empty required-net evidence and missing points are not a pass.
- A listed debug header with kind `none` does not satisfy a required header.
