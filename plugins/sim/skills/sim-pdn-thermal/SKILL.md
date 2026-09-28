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
## PDN field reference

`pdn.rails[]` declares a `name`, `source_v` (V), `source_node`, unique `nodes`, `branches`, and `loads`. Set at least one of `max_drop_v` (V) or `max_drop_pct` (%); `temperature_c` is °C and defaults to 25. A separate `return_source_node` enables explicit return-path solving.

| Branch/load field | Meaning and units |
| --- | --- |
| Branch topology | `ref`, `from_node`, `to_node`, and `kind`: `trace`, `plane`, `via`, `resistor`, or `wire`. |
| Trace/plane geometry | `length_mm`, `width_mm`, and either `copper_oz` or `thickness_um`; `layer` is `external` or `internal`. |
| Via data | `length_mm`, `count`, `drill_mm`, `plating_um`, and optional `via_max_a` (A). |
| Resistance/wire | `resistance_ohm`, or wire `length_m`, `resistance_ohm_per_km`, optional `ampacity_a` (A). |
| Trace rule | `allowed_rise_c` (°C, default 10). |
| Load | `node`, `current_a` (A) or `import:<net>`, optional `min_v` (V), and optional `return_node`. |

## Thermal field reference

`thermal.ambient_c` is ambient temperature in °C. Each `components[]` item declares `ref`, `power_w` (W), `tj_max_c` (°C), optional `derating_margin_c` (°C), and either `path` or network placement. A scalar `path` uses `theta_ja_c_per_w` or the series `theta_jc`, `theta_cs`, `theta_sa` (each °C/W). A `network` declares `nodes`, `ambient_node`, positive `{a,b,c_per_w}` edges (°C/W), and `power_nodes` (W).

```json
{
  "schema_version": 1,
  "name": "power-thermal-reference",
  "pdn": {
    "rails": [
      {
        "name": "VDD",
        "source_v": 5.0,
        "max_drop_v": 0.2,
        "source_node": "source",
        "nodes": ["source", "load"],
        "branches": [
          {
            "ref": "R1",
            "from_node": "source",
            "to_node": "load",
            "kind": "resistor",
            "resistance_ohm": 0.1
          }
        ],
        "loads": [{"node": "load", "current_a": 1.0}]
      }
    ]
  },
  "thermal": {
    "ambient_c": 25.0,
    "components": [
      {"ref": "U1", "power_w": 1.0, "tj_max_c": 125.0, "path": {"theta_ja_c_per_w": 30.0}}
    ]
  }
}
```

## Gates, formulas, and assumptions

PDN gates are `pdn.<rail>.drop.<load-node>`, `pdn.<rail>.ampacity.<branch-ref>`, and `pdn.<rail>.network`. Thermal gates are `thermal.<component>.tj`, `thermal.network`, or `thermal.components`. `pass` meets the declared voltage/ampacity/junction limit; `fail` exceeds it; `unknown` means an import is unresolved, the network is singular, or required data cannot be solved.

Trace resistance uses `R = ρL/(wt) × [1 + α(T − 20 °C)]`, with copper `ρ = 1.724×10⁻⁸ Ω·m` at 20 °C and `α = 0.00393 K⁻¹`; one ounce copper is 34.79 μm. Trace ampacity uses the IPC-2221 screening relation `I = k ΔT^0.44 A^0.725`, where `A` is cross-section in mil², `ΔT` is allowed rise in °C, `I` is A, `k = 0.048` external and `0.024` internal. It is a rule estimate, not an electrothermal solver. Thermal rise is `P θ`; network solves use nodal conductance with ambient fixed as reference.

## Pitfalls

- A rail needs an explicit voltage-drop limit and a connected return/reference path.
- Do not give imported wire branches fabricated dimensions; resolve their length, resistance, current, and ampacity from validated contracts.
- Connectivity-derived current references use `import:<net>`; unresolved values remain unknown.
- Copper and resistance assumptions are approximations; do not infer board temperatures from the ampacity rule.
