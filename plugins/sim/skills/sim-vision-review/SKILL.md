---
name: sim-vision-review
description: Look at every generated plot, intake image, and sister render and record a checked vision review.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - vision review
  - look at the plot
  - sim-record-vision-review
---
## When to look

Run a vision review for **every** image the agent reads: each PNG under
`out/<name>/plots/`, every attachment intake image, and every sister render
(circuit schematic, mechanical drawing, wire board view, UX mockup) cited as
evidence. An unread image is not evidence.

## Checklists

Each review names a checklist slug and records findings against it:

| Checklist | Judge |
| --- | --- |
| `sim-summary` | summary.png counts vs. report checks, legend not covering bars, integer ticks |
| `margin-chart` | measured marker vs. bound line, shaded allowed side, limit text, clipped values flagged |
| `spice-waveform` | waveform vs. .meas bound lines and `AT=` markers, decade labels, unit conversion (dB) |
| `rf-sparams` | band windows vs. traces, dB scale, tick labels inside the canvas |
| `dft-testpoints` | pad scale, top/bottom legend, pitch outline overlaps, failing-pair lines |
| `fem-deflection` | deflection curve monotone toward the tip, sample density, tip annotation and limit (an off-scale limit shows as a dashed edge line labeled `(above)`/`(below)`) |
| `intake-image` | content readable, relevant to the request, no secrets in frame |
| `sibling-render` | render matches the sister export it claims to show, labels legible |

## Recording

Call `sim_record_vision_review` (or `sim record vision-review --json`) with
either `image_path` + `image_sha256` for a file, or `source_event_id` to cite
a recorded image observation. Findings carry `category`, `severity`
(`info|warn|error`), and `note`. The `impression` field is long-form prose:
**at least 400 characters and at least three sentences** describing what was
seen, what it means for the analysis, and what to do next — terse one-liners
are rejected by the record validator.

```json
{
  "schema_version": 1,
  "name": "vision-review-demo",
  "dft": {
    "nets": ["VCC", "GND"],
    "required": "all",
    "test_points": [
      {"ref": "TP1", "net": "VCC", "x_mm": 5, "y_mm": 5, "pad_diameter_mm": 1.0, "side": "top"},
      {"ref": "TP2", "net": "GND", "x_mm": 10, "y_mm": 5, "pad_diameter_mm": 1.0, "side": "bottom"}
    ],
    "min_pitch_mm": 2.54,
    "require_debug_header": false
  }
}
```

Running this brief produces `dft-testpoints.png`; the review then checks pad
scale, pitch outlines, and the top/bottom legend against `dft-testpoints`.

## Advisory only

Vision findings are advisory evidence. They never change a deterministic
gate verdict and never promote an `unknown` or `fail` to `pass`.
