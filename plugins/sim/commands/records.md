---
name: records
description: Record VibeBB decisions, impressions, and vision reviews or show record status.
---
Run `python3 plugins/sim/scripts/sim_launcher.py record decision|impression|vision-review --json <record>` to append a VRP v1 record, or `record status` to summarize `observations/sim/`. Every record needs an impression of at least 400 characters and three sentences. Use `/sim:records` whenever a decision, a stage close-out, or an image review would otherwise be lost.
