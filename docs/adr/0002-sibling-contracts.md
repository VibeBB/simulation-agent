# ADR-0002: Exchange sibling data through strict JSON mirrors

- Status: Accepted
- Date: 2026-03-05

## Context

Circuit, mechanical, wire, and bard agents are independently versioned. Sharing
Python models would create runtime coupling and make plugin deployment order
observable.

## Decision

Exchange versioned JSON in the workspace. Maintain strict local mirror
Pydantic models for v1 connectivity, mechanical envelope, wire contract, and
simulation request/response files. Record the original path and SHA-256 of
each accepted import. Unknown or unsupported content, including unmodeled
bard artifacts, is not inferred or partially accepted.

## Consequences

Each agent can evolve independently while preserving an auditable boundary.
When a sibling changes its JSON schema, update the mirror deliberately and add
compatibility tests; do not load its Python package at runtime.
