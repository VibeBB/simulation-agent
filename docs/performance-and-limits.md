# Performance and limits

## Solvers

- **ngspice**: subprocess batch run; `timeout_s` per deck (default 120 s).
  `.meas` results are parsed from stdout; waveforms come from a
  `raw.bin` written by an appended `.control` block (ngspice-36 refuses
  `.meas` together with `-r` in batch mode). Decks that already contain a
  `.control` section produce no raw file — `plot_errors` notes it and no
  transient plot is emitted.
- **CalculiX**: subprocess `ccx` on a generated cantilever `.inp`;
  `parse_dat` reads nodal results. Only the cantilever box case is
  supported; `.frd` field output is not parsed, so no stress/displacement
  field plots exist.
- **KiCad-rfsim / openEMS**: optional (`sim-tools-em` image); the lockfile
  entry for `sim-tools-em` is still `reserved: null` — publishing waits on
  a CI build-time/cost decision.

## Analysis limits

- WCA Monte Carlo: seeded, samples count bounded by the brief; samples are
  not retained, so no MC histogram plot exists.
- PDN/thermal: dense `linalg.solve` on small nodal systems; the thermal
  network graph itself is not rendered.
- RF: Touchstone v1 only; no v2, no mixed-mode parameters.
- Expressions (`expr.py`): a restricted arithmetic AST — no function
  calls, no attribute access.
- Plots: 5×7 raster font, no anti-aliasing; at most `MAX_PLOT_IMAGES` (8)
  inline PNGs per MCP response (`plots_omitted` notes truncation); every
  PNG is deterministic (zlib level 9, no timestamps).
- FEM plot: 100-sample deflection curve plus the CalculiX tip value; the
  analytic Euler–Bernoulli estimate is a sanity bound, not a substitute
  for a real FE model.
- Vision-review quality is checked only by the prose/record rules —
  nothing verifies the review actually describes the image.

## Docker image

`sim-tools` is the pinned runtime for every plugin command (Docker-only,
ADR-0008); first `prewarm`/`docker run` costs the image pull and a short
container startup, then per-command overhead is the container exec.
Image contents and sizes are documented in [operations.md](operations.md)
and `docker/README.md`.
