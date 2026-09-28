# ADR-0003: Use fail-closed three-valued verdicts

- Status: Accepted
- Date: 2026-03-05

## Context

Simulation outputs are meaningful only when the declared input, predicate, and
measurement all exist. Treating absent evidence as success would be unsafe.

## Decision

Every check is `pass`, `fail`, or `unknown`. Aggregate any `fail` as `fail`;
otherwise aggregate any `unknown`, or an empty check set, as `unknown`; return
`pass` only when at least one check ran and every check passed. Missing tools,
inputs, thresholds, measurements, and output files are unknown.

## Consequences

Callers must resolve unknown evidence before accepting a design. A successful
process exit or an agent's narrative cannot override gate results.
