---
name: records
description: Record VibeBB decisions, impressions, and vision reviews or show record status.
---
Run `python3 plugins/sim/scripts/sim_launcher.py record decision|impression|vision-review|reconcile|insight|song-receipt|read --json <record>` to append a VRP v2 record, `record status` to summarize `observations/sim/`, or `record digest` / `record search --json <query>` to read sister records. Every record needs an impression of at least 400 characters and three sentences. Use `/sim:records` whenever a decision, a stage close-out, or an image review would otherwise be lost.
