---
name: ux-inbox
description: List SLP v2 UX-creator requests and answer them with ux-respond.
---
Run `python3 plugins/sim/scripts/sim_launcher.py ux-inbox` to list requests under `liaison/` with states `new`, `blocked`, `answered`, and `stale`, plus malformed files. Answer a request with `ux-respond --json '{"request": "<id>", "status": "<status>", ...}'`; `done` requires reports or artifacts, pass gate verdicts, and valid decision/impression record refs.
