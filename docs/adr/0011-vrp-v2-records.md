# ADR-0011: VRP v2 records and blind render review

Status: Accepted
Date: 2026-10-11

## Context

VRP v1 (ADR-0009) let a model append free prose that nobody had to answer:
logs could be edited or truncated unnoticed, the same concern could be raised
forever, a rejected idea could come back unchanged, and one vision review of a
plot was taken as seen. wire-agent shipped VRP v2 as the family
reference; the user chose to port all of it to every plugin.

## Decision

- Copy the canonical v2 hooks (`_records.py`, `require_records.py`,
  `blind_guard.py`) byte-for-byte from wire-agent and mirror `_records.py`
  as `src/sim/_vrp.py`. Ruff skips these files;
  `scripts/check_shared_hooks.py` pins the digests and `tests/test_records.py`
  pins the mirror to the hook bytes.
- `src/sim/records.py` keeps the typed pydantic writers and `RECORDERS`,
  delegating validation to `_vrp.py`. `decision_event_ids` and
  `impression_event_ids` replace `valid_event_ids` v1 re-validation for
  `liaison.py` and `responses.py`; they read only intact chains, so a
  forged appended line refuses every reference instead of passing one.
- `out/**/plots/*.png` is the dual-review glob: `sim-blind-review` records
  the blind round behind `blind-guard`, and the caller reconciles.
- sim only receives bard songs (`song-receipt`); a receipt never asks for
  another one. `protect-generated` makes `liaison/*.bard-song.json` and the
  new logs append-only.
- The CLI and MCP server gain `reconcile`, `insight`, `song-receipt`, `read`,
  `digest` and `search`.

## Consequences

Records remain advisory: no gate reads them. Existing v1 logs are archived as
`<name>.v1.jsonl` on the first v2 write. Callers that recorded impressions with
the v1 shape now get a validation error naming the missing v2 fields.
The vendored core adds about 1,000 statements to `src/sim`; measured as CI
measures (no ngspice or CalculiX on `PATH`) every structural floor and
`fail_under` still holds, so none was lowered.
