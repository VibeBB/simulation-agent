---
name: plots
description: Show a simulation output directory's PNG plots inline and record a vision review.
---
Run `python3 plugins/sim/scripts/sim_launcher.py plots <out_dir>` to emit `sim-report.json` plot paths and hashes for the analysis run in `<out_dir>` (for example `out/buck_regulator`). Look at every PNG and record a `sim_record_vision_review` per plot with the matching checklist slug before citing any plot as evidence.
