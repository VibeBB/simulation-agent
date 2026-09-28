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
## EMC field reference

| Field | Meaning and units |
| --- | --- |
| `interfaces[]` | `connector_ref`, explicit `nets[]`, optional `esd_level` 1–4, and required `external` boolean. |
| `protections[]` | `ref`, `nets[]`, `vrwm_v` and `vclamp_v` (V), `esd_rating_contact_kv` (kV), `distance_to_connector_mm` (mm). |
| `protected_devices[]` | `ref`, `nets[]`, and `abs_max_v` (V). |
| `signals[]` | `net`, optional `v_max` (V), `rise_time_ns` (ns), `length_mm` (mm), `er_eff`, and `terminated`, `high_speed`, `reference_plane_continuous` flags. |
| `decoupling[]` | `ic_ref`, `power_pins[]`, and capacitor `{ref, distance_mm}` records. |
| Section limits | `max_tvs_distance_mm` (default 10 mm), `max_decap_distance_mm` (default 5 mm), and `min_caps_per_pin` (default 1). |

```json
{
  "schema_version": 1,
  "name": "emc-reference",
  "emc": {
    "interfaces": [
      {"connector_ref": "J1", "nets": ["VIN"], "esd_level": 2, "external": true}
    ],
    "signals": [
      {
        "net": "VIN",
        "v_max": 12.0,
        "rise_time_ns": 1.0,
        "length_mm": 5.0,
        "er_eff": 4.0
      }
    ]
  }
}
```

## Gates, formulas, and assumptions

`emc.interface.<ref>` is `unknown` when an imported connector has no interface declaration: declare that connector's nets explicitly. Connectivity imports have no connector-to-net mapping, so imported nets never create interfaces or signal records. An imported net may fill only `v_max` for an already-declared interface signal whose brief omits it.

`emc.protection.<connector>.<net>` compares TVS working voltage with net `v_max`, clamp voltage with a declared protected-device absolute maximum, connector distance with the section limit, and contact rating with the IEC level when declared. The v0.1 mapping for IEC 61000-4-2 contact levels 1–4 is 2, 4, 6, and 8 kV. These are screening thresholds, not a complete immunity test plan.

`emc.critical_length.<net>` is emitted only when `length_mm`, `rise_time_ns`, or `high_speed` is declared. It uses

`l_critical_mm = rise_time_ns × 299.792458 mm/ns / (6 × √er_eff)`.

With length and rise time present, the check passes when length is at most critical length or the signal is terminated. Partial timing data, including `high_speed: true` without both length and rise time, is `unknown`. `emc.reference_plane.<net>` evaluates high-speed continuity. `emc.decoupling.<ic>.<pin>` checks capacitor count and maximum placement distance; `emc.inputs` is unknown when no EMC predicate can be evaluated.

Across gates, `pass` meets the declared predicate, `fail` violates it, and `unknown` means necessary voltage, limit, timing, or connector-net facts are absent. These are deterministic rule checks, not conducted/radiated emissions or immunity simulations.

## Pitfalls

- Never assign every imported net—including ground or power—to every imported connector.
- Do not synthesize `EmcSignal` records from imported net classes.
- Declare both edge timing and trace length for a critical-length decision; do not infer them from a net name.
- `er_eff` defaults to 4.0 in the model; replace that default with supported board evidence when the actual stackup differs.
