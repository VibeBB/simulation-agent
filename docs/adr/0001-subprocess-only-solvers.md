# ADR-0001: Run solvers only as unmodified subprocesses

- Status: Accepted
- Date: 2026-03-05

## Context

ngspice is available as a batch executable. CalculiX, openEMS, and CSXCAD are
copyleft tools; in-process bindings would couple the BSD-3-Clause package to
their implementation and complicate licensing and runtime isolation.

## Decision

Invoke each third-party solver as an unmodified, bounded subprocess. Keep all
input generation, parsing, deterministic calculations, and verdict logic in
the BSD-licensed `src/sim/` package. Apply explicit timeouts and map missing
executables, non-zero exits, parse failures, and missing expected output to
`unknown`.

## Consequences

Solver version and process output are auditable in reports. Host execution
remains possible, while Docker provides a reproducible solver environment.
No solver library or sibling package may be imported by the runtime.
