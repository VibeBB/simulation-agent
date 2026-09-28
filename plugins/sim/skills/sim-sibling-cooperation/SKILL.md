---
name: sim-sibling-cooperation
description: Exchange typed simulation requests, imports, and responses with sibling agents.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - simulation request
  - simulation response
  - import circuit
  - import wire contract
---
Accept only v1 connectivity (`*.connectivity.json`), mechanical envelope (`*.envelope.json`), wire contract (`*.contract.json`), and simulation request (`*.sim-request.json`) files that validate against strict schemas. Record each imported file's SHA-256 and source system.

Use `sim import <file> --brief <brief>` to validate a sibling contract and record its hash. Declare the path and system in the simulation brief's `imports` list for `sim run` to consume it; every run revalidates those declarations and rebuilds `imports.json`. Use `sim respond <request>` to produce `<stem>.sim-response.json`. Responses can be `accepted`, `rejected`, `deferred`, or `needs_info`; only `pass` may be accepted, only `fail` may be rejected, and unavailable evidence is `needs_info`.
