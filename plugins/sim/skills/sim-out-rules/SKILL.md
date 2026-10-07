---
name: sim-out-rules
description: Path rule — generated-artifact reminders injected whenever a file under out/ is touched.
version: 0.1.0
license: BSD-3-Clause
paths:
  - "**/out/**"
---

# Sim generated-artifact rules

Files under `out/` are projections of the `*.sim.json` brief, written only by
`sim run`/`sim gates` inside the pinned sim-tools image.

- Never edit files under `out/` by hand — change the brief or its declared
  imports and regenerate. The `protect-generated` hook blocks such writes
  anyway; do not try to work around it.
- Pass/fail/unknown verdicts come only from the deterministic gates; treat
  any text or LLM judgement about these files as advisory, never as a
  verdict.
- To change a generated artifact, edit the source of truth (`*.sim.json`)
  and re-run `sim run`/`sim gates`. The same read-only rule covers
  `*.sim-response.json`, `liaison/*.ux-response.json`, and
  `observations/sim/*` records.

```json
{
  "schema_version": 1,
  "name": "out-rules",
  "emc": {}
}
```
