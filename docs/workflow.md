# Workflow

The working loop has seven stages. Each stage names the tool that performs
it and the records it is expected to leave behind (see
[records-and-vision.md](records-and-vision.md)); the require-records Stop
gate enforces the protocol at session end.

## 1. intake

User files and attachments enter the workspace. The `intake-attachments`
hook materializes attached images under `intake/attachments/` with a
`manifest.jsonl` provenance line; viewing one records an image observation
that a vision review can cite. Values read off images are assumptions, not
solver output — the user must confirm them before they become brief bounds.

## 2. brief

The agent authors a `*.sim.json` brief (`sim_validate_brief` / `sim schema`
to check it) from explicit project evidence. Every section is optional but
at least one is required; every limit must be stated, not inferred.

## 3. imports

Sister artifacts (circuit connectivity, mech envelope, wire harness, thermal
sources) are mirrored into `imports[]` via `/sim:import <file> --brief
<brief>` (`sim_import` / `import_source`); the import is bound to the file's
sha256 in `imports.json`.

## 4. analysis

`/sim:run <brief>` (`sim_run`) executes every declared section; focused
commands run one (`sim_spice` … `sim_rf`). Outputs land in `out/<name>/`:
`sim-report.json` v2 (checks, measures, plots, plot_errors), `sim-report.md`
with a Plots section, `manifest.json`, `provenance.json`, adapter artifacts
(`raw.bin`, `.dat`, …), and `plots/*.png`.

## 5. review

`/sim:gates` aggregates the verdict. The agent (and sim-review) then
**looks at every plot** and records a `vision_review` per image with the
matching checklist slug (see the sim-vision-review skill). Review may
surface stale or missing evidence but cannot change a verdict.

## 6. liaison

`/sim:ux-inbox` lists SLP v2 requests with states new/blocked/answered/
stale; `/sim:ux-respond` (`sim_ux_respond`) answers them, enforcing the
protocol's `done`/`needs_info` rules and validating decision/impression
refs against `valid_event_ids`. v1 sister requests are answered by
`/sim:respond` (`sim_respond`), which reruns the requested analysis and
writes a `*.sim-response.json` v2.

## 7. revision

When inputs change, stale answers and reports are regenerated. Records
accumulate; each `record decision|impression|vision-review` line is
re-validated and hash-chained at write time, and `sim_records_status`
shows what the Stop gate still expects.
