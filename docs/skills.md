# Skills

Engineering guidance for the agents lives under `plugins/sim/skills/`; each
`SKILL.md` carries a `version:` and embeds at least one ```json block that
validates as a `SimulationBrief` (enforced by `tests/test_skill_docs.py`).

| Skill | Coverage |
| --- | --- |
| `sim-brief` | authoring `*.sim.json` briefs, section selection, limit declaration, EMC interface-net declaration |
| `sim-workflow` | end-to-end intake→brief→imports→analysis→review→liaison→revision flow, the command set, VRP record rules |
| `sim-spice` | SPICE decks, `.meas` limits, solver failure handling, tolerance analysis |
| `sim-pdn-thermal` | PDN DC drop/ampacity and thermal resistance-path/network guidance |
| `sim-wca` | worst-case analysis: EVA/RSS/Monte Carlo, restricted expression grammar |
| `sim-emc-esd` | TVS selection, placement, critical-length and reference-plane rules, decoupling |
| `sim-dft` | test-point coverage, pad size, pitch, debug headers, boundary scan |
| `sim-fem-calculix` | cantilever FEM geometry/material/mesh, CalculiX vs. analytic comparison |
| `sim-rf-openems` | Touchstone band checks, KiCad-rfsim/openEMS subprocess, microstrip estimate |
| `sim-sibling-cooperation` | exchanging typed requests, imports, and responses with sister agents |
| `sim-vision-review` | when to look at every image, the checklist slugs, the 400-char/3-sentence impression rule, advisory-only findings |
| `sim-brief-rules` | path rule on `**/*.sim.json` / `**/*.sim-request.json` — schema, strict request validation, and provenance reminders injected when a brief or sister request is touched |
| `sim-out-rules` | path rule on `**/out/**` — generated artifacts are read-only projections; change the brief and regenerate (the `protect-generated` hook enforces) |

See [commands.md](commands.md) for the command surface and
[records-and-vision.md](records-and-vision.md) for the record protocol the
skills reference.
