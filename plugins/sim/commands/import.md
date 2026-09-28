---
name: import
description: Validate a sibling connectivity, mechanical envelope, or wire contract import.
---
Run `python3 plugins/sim/scripts/sim_launcher.py import <file> --brief <brief>` to validate the sibling contract and record its SHA-256 digest. To consume an import during `sim run`, declare its path and system in the brief's `imports` list; each run rebuilds `imports.json` from those validated declarations.
