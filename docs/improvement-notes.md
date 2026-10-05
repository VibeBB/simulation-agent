# Improvement notes

Running list of what changed in this refactor and what is still open.

## Done in this refactor

- VRP v1 records port (decisions, stage impressions, vision reviews)
  with the `require-records` Stop gate and hook mirror validation.
- Deterministic stdlib-only PNG plots for every analysis, inline MCP
  images (sha256-verified, ≤8 per response), and image-observation
  records from all `sim_*` tools.
- SLP v2 UX-creator inbox/respond (`liaison/`) with states, strict
  request schema, cross-responder dependencies, and a session-start
  inbox notice.
- v1 `*.sim-response.json` schema v2: request/brief sha256 binding and
  validated `decision_refs`; wider `from_system` literal set.
- `valid_event_ids`: refs are checked against *valid* record lines
  (recomputed event_id), not just present ones.
- Docker-only launcher (host/auto removed, ADR-0008).
- Real MCP tool descriptions instead of placeholders.
- `VisionInspectTool` on sim-analyst and sim-review with matching
  record-image-observation matchers.
- cache-sweep Trivy key fix (runner-scoped week key).
- AGENTS.md / operations.md stale facts (uv version, hook counts,
  Docker-only mode).

## Remaining (with reasons)

- `sim-tools-em` (openEMS) lock entry still `reserved: null` — publishing
  needs a CI build-time/cost decision.
- Plots use a 5×7 raster font without anti-aliasing — deterministic and
  dependency-free; a renderer upgrade is a deliberate trade-off.
- No FEM stress/displacement field plot: CalculiX `.frd` field output is
  not parsed.
- No transient plot for user `.control` decks: those decks are rejected
  for raw output by design (their control block would conflict).
- WCA Monte Carlo histogram not plotted: samples are not retained after
  the seeded run.
- No thermal-network graph render: the nodal graph is checked, not drawn.
- Vision-review quality is only prose-rule checked — nothing verifies
  the review describes the image.
- Sister work needed: UX-creator must emit SLP v2 requests (the schema is
  frozen here); circuit/mech/wire exports could carry their own sha256
  manifest — sim hashes every input on read today.
