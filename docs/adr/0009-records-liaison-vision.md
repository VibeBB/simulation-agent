# ADR-0009: VRP records, SLP liaison, and deterministic vision plots

- Status: Accepted
- Date: 2026-10
- Related: ADR-0002 (sister contracts), ADR-0004 (vision hooks), ADR-0008 (Docker-only launcher)

## Context

The sister plugins converged on a shared VibeBB record protocol (VRP v1)
for auditable agent work, an SLP v2 liaison protocol for ux-creator-driven
multi-agent requests, and inline vision evidence for anything an agent is
asked to look at. `sim` previously had none of these: no record trail, no
UX inbox, and plots it generated could not be inspected or cited.

## Decision

- Port VRP v1 into `src/sim/records.py` with the same envelope, hashing,
  and prose rules as the canonical wire-agent implementation; the
  `require-records` Stop hook enforces it.
- Implement SLP v2 in `src/sim/liaison.py`: strict frozen `UXRequest`/
  `UXResponse` models, inbox states (new/blocked/answered/stale/malformed),
  cross-responder `depends_on`, and `done` rules bound to valid record
  refs via `valid_event_ids`.
- Render deterministic PNG plots in `src/sim/plot.py` (stdlib only —
  no third-party imaging), attach them to `sim-report.json` v2, and return
  up to 8 sha256-verified inline images from image-capable MCP tools.
- Upgrade `*.sim-response.json` to schema_version 2 (request/brief sha256,
  validated `decision_refs`) while keeping the v1 request flow unchanged.

## Consequences

Every gate run leaves inspectable evidence; every answered request can be
traced to records; forged or mutated record lines are refused as refs.
Trade-offs and leftovers are tracked in
[../improvement-notes.md](../improvement-notes.md).
