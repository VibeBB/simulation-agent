---
name: sim-wca
description: Worst-case analysis methods, parameter tolerances, and reproducible sampling.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - worst-case analysis
  - WCA
  - tolerance stack
  - Monte Carlo
---
## WCA field reference

`parameters[]` uses a unique `name`, `nominal`, and exactly one of `tol_abs` or `tol_pct`. Both tolerances are in the parameter's unit; `tol_pct` is percent. Optional `temp_coeff_ppm` (ppm/°C) and `temp_range_c` (°C) must appear together. `distribution` is `uniform` or `normal`.

Each `outputs[]` item declares exactly one `expression` or `spice_measure`, a unique `name`, and optional inclusive `min`/`max` bounds in the output unit. `methods[]` selects unique `EVA`, `RSS`, and/or `MC`; `max_vertices`, `mc_samples`, `seed`, and `spice_mc_samples` control reproducible work.

```json
{
  "schema_version": 1,
  "name": "wca-reference",
  "wca": {
    "parameters": [{"name": "R1", "nominal": 1000.0, "tol_pct": 5.0}],
    "outputs": [
      {
        "name": "vout",
        "expression": "5 * 1000 / (R1 + 1000)",
        "min": 4.5,
        "max": 4.8
      }
    ],
    "methods": ["EVA", "RSS", "MC"],
    "mc_samples": 1000,
    "seed": 17,
    "max_vertices": 4096
  }
}
```

## Methods, gates, and semantics

The absolute delta is `Δ = tol_abs` or `|nominal| × tol_pct/100`, plus `|nominal × temp_coeff_ppm/10⁶| × temp_range_c` when temperature terms are supplied. For a normal distribution, the declared delta represents ±3σ. EVA evaluates all `2ⁿ` parameter vertices up to `max_vertices`. RSS estimates first-order output spread by central-difference sensitivities: `σ_out ≈ √Σ(Sᵢ Δᵢ)²`. MC uses `random.Random(seed)`; uniform samples span `nominal ± Δ`, while normal samples use standard deviation `Δ/3`.

Gate IDs are `wca.<method>.<output>`. `pass` means the complete estimated range is within bounds; `fail` means it crosses a bound; `unknown` means no acceptance bound, invalid expression/measurement, or a vertex/sample cap is exceeded. SPICE-measure outputs use one isolated ngspice process per corner/sample and obey `spice_mc_samples`.

## Pitfalls

- Normal tolerance is ±3σ, not ±1σ; do not apply a second tolerance conversion.
- EVA grows exponentially; configure caps rather than silently reducing its corner set.
- RSS is a local linear approximation; it can miss strongly nonlinear or discontinuous behavior.
- Monte Carlo bounds are sample extrema, not a proof of global worst case.
- Keep the seed and sample count fixed when comparing reports.
