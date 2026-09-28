---
name: sim-spice
description: SPICE and tolerance-analysis workflow, measurements, and solver failure handling.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - ngspice
  - SPICE
  - circuit transient
  - WCA
---
## SPICE field reference

`spice.deck` requires exactly one of `netlist_path` (workspace-relative) or `elements[]`. A generated element uses `ref`, `kind` (`R`, `C`, `L`, `V`, `I`, `D`, `X`), `nodes[]`, `value`, and optional `model`. `models[]` accepts one-line `.model` or `.include` statements. `analyses[]` must contain at least one supported single-line `.ac`, `.dc`, `.noise`, `.op`, `.pz`, `.tf`, or `.tran` directive. `timeout_s` is seconds (default 120).

Each `measures[]` item has `name`, a complete one-line `.meas`/`.measure` `statement`, and optional inclusive `min`/`max` limits in the output's units. The statement must name the declared measure.

```json
{
  "schema_version": 1,
  "name": "spice-reference",
  "spice": {
    "deck": {
      "netlist_path": "circuits/divider.cir",
      "analyses": [".tran 10n 10u"],
      "measures": [
        {
          "name": "vout",
          "statement": ".meas tran vout FIND v(out) AT=1u",
          "min": 3.1,
          "max": 3.2
        }
      ],
      "timeout_s": 30
    }
  }
}
```

## Gates, assumptions, and pitfalls

`spice.<measure>` parses ngspice's reported scalar and compares it with declared bounds. `pass` is within bounds, `fail` is outside them, and `unknown` means the solver failed, timed out, emitted a failed/missing/non-finite measure, or the measure has no acceptance bound. No declared measure produces `spice.measurements` unknown.

The adapter launches unmodified `ngspice` in batch mode. Declared one-line analyses and measures replace their source-deck counterparts; `.control` blocks and multi-line directives are unsupported. SPICE model accuracy remains the netlist author's responsibility.

- Do not invent model cards, initial conditions, parasitics, or operating conditions.
- Keep all referenced files within the workspace and preserve includes.
- Tolerance analysis changes only declared `.param` lines; model-card and instance parameters are not substituted.
- A clean subprocess exit without a parsed, bounded `.meas` result is not a pass.
