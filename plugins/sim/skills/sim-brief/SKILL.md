---
name: sim-brief
description: Simulation brief schema, required evidence, and fail-closed input rules.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - simulation brief
  - simulation schema
  - analysis limits
---
## Brief contract

Run `sim schema` for the exact v0.1 JSON Schema. Files use the `*.sim.json` suffix; unknown fields, non-finite numbers, and unsupported values are errors. At least one analysis section is required. File references are workspace-relative.

| Field | Meaning and units |
| --- | --- |
| `schema_version` | Required integer literal `1`. |
| `name` | Required report name; letters, digits, `_`, and `-` only. |
| `description` | Optional project context; it does not affect calculations. |
| `imports` | Optional `{path, system}` records, where `system` is `circuit`, `mech`, `wire`, or `bard`. |
| `spice`, `pdn`, `thermal`, `wca`, `emc`, `dft`, `fem`, `rf` | Optional section objects; each section has its own field and unit reference in its skill. |

```json
{
  "schema_version": 1,
  "name": "brief-reference",
  "description": "A partial brief with an intentionally empty EMC section.",
  "emc": {}
}
```

## Gate interpretation

Section gates are named `spice.<measure>`, `pdn.<rail>.*`, `thermal.<ref>.tj`, `wca.<method>.<output>`, `emc.*`, `dft.*`, `fem.*`, and `rf.*`. `pass` means supplied inputs meet the implemented predicate; `fail` means a measured or computed limit is violated; `unknown` means required evidence, a tool, or a supported calculation is missing. An empty section can be valid JSON yet still yield `unknown`.

The brief schema validates declarations, not their engineering adequacy. Formulas, units, and simplifications are documented by the relevant section skills. A successful parse is never evidence of a passing engineering gate.

## Pitfalls

- Do not guess geometry, operating points, material properties, ratings, or acceptance bounds.
- Declare a threshold for every result that must be judged; an unbounded measurement remains `unknown`.
- Do not treat a sister connectivity import as a connector-to-net map; explicitly declare EMC interface nets.
- Unsupported features and missing solver output remain `unknown`, not approximated values.
