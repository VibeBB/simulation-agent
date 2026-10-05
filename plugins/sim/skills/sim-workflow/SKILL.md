---
name: sim-workflow
description: Safe end-to-end workflow for deterministic simulation brief authoring and gates.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - simulation brief
  - run simulation
  - simulation report
---
## End-to-end flow

1. Run `/sim:doctor`; use strict mode when a solver is required for acceptance. Record missing tools before choosing analyses.
2. Gather source artifacts, operating conditions, material/geometry facts, and explicit limits. Use `/sim:import <file> --brief <brief>` for supported sister contracts; add the same path and system to `imports[]`.
3. Author a workspace-relative `*.sim.json` brief using only supported evidence. Validate with `sim validate <brief>` or inspect the model using `sim schema`/the `sim_schema` MCP tool.
4. Execute `/sim:run <brief>` for every declared section or one focused command (`/sim:spice`, `/sim:pdn`, `/sim:thermal`, `/sim:wca`, `/sim:emc`, `/sim:dft`, `/sim:fem`, `/sim:rf`).
5. Use `/sim:gates <brief>` for the complete gate summary. Review `out/<name>/sim-report.json`, `sim-report.md`, `provenance.json`, and `manifest.json`; cite gate IDs, measurements, tools, and source hashes.
6. For a sister request, run `/sim:respond <request.sim-request.json>` and return the generated response path. A deterministic `pass` is `accepted`, `fail` is `rejected`, and `unknown` or missing evidence is `needs_info`.

The OpenHands command set is `/sim:doctor`, `/sim:run`, `/sim:gates`, `/sim:import`, `/sim:respond`, `/sim:ux-inbox`, `/sim:plots`, `/sim:records`, `/sim:spice`, `/sim:pdn`, `/sim:thermal`, `/sim:wca`, `/sim:emc`, `/sim:dft`, `/sim:fem`, and `/sim:rf`. Commands use the installed plugin launcher; the equivalent source-tree form is `python3 plugins/sim/scripts/sim_launcher.py <subcommand> ...`.

```json
{
  "schema_version": 1,
  "name": "workflow-reference",
  "dft": {
    "nets": ["VIN"],
    "required": "all",
    "test_points": [
      {
        "ref": "TP1",
        "net": "VIN",
        "pad_diameter_mm": 1.0,
        "x_mm": 10.0,
        "y_mm": 5.0,
        "side": "top"
      }
    ],
    "require_debug_header": false
  }
}
```

## Gate semantics and pitfalls

The top-level `schema_version` is `1`; `name` identifies report outputs; `description` is context; `imports` list strict `{path, system}` records; analysis objects are `spice`, `pdn`, `thermal`, `wca`, `emc`, `dft`, `fem`, and `rf`. Each analysis skill defines its fields and units. A brief must contain at least one section.

Across all analyses, `pass` means the implemented deterministic predicate meets the declared criterion, `fail` means it violates a criterion, and `unknown` means required facts, solver evidence, supported input, or an acceptance bound is missing. A clean exit or plausible narrative cannot promote unknown to pass.

- Do not edit generated `out/` files; rerun from validated inputs.
- Keep solver availability and model assumptions visible in the report.
- Never invent acceptance criteria to silence a failing or unknown gate.
- Treat the analytic PDN, thermal, EMC, DFT, WCA, and microstrip checks as models/rules—not a substitute for physical qualification.

## Records you must leave (VibeBB Record Protocol — mandatory, unprompted)

Record these without being asked; the Stop hook refuses to finish a
session that still owes them.

- **Decision** (`sim_record_decision`) for every engineering choice:
  analytic model versus solver run, the source of acceptance bounds,
  derating and temperature assumptions, mesh density and element type,
  Monte Carlo sample count and seed, which sister import is
  authoritative, or declaring a value unknown instead of guessing. The
  record carries the question, the first principles / physical laws /
  standards it rests on, at least two options with pros and cons, the
  chosen option, a rationale of 200+ characters, evidence (artifact paths
  are hashed; cite datasheets or standards as references), assumptions,
  unknowns, residual risks and the observation that would reopen it.
- **Stage impression** (`sim_record_impression`) when a stage ends,
  after its final regeneration: 400+ characters and 3+ sentences on what
  you noticed, what works, what worries you, how a maker or user would
  read the result, and what to do next. Bind it to the stage's output
  directory (`out/<name>`) or the files it produced so the impression is
  bound to their sha256. Stage slugs: intake, brief, imports, analysis,
  review, liaison, revision.
- **Vision review** (`sim_record_vision_review`) every time you look at
  an image — a plot under `out/<name>/plots/`, an intake attachment, a
  sister render, an `inspect_image_with_vision` answer: findings plus a
  long-form impression of 400+ characters, bound to `image_path` or to
  the vision event's `source_event_id`. Use the checklist slug that
  matches what you viewed (see the plot checklists).

Records are advisory evidence: they never change a gate verdict.
`sim_records_status` shows what is still owed.
