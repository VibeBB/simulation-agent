# ADR-0005: Publish and run sim-tools by digest

- Status: Accepted
- Date: 2026-09-30

## Context

The `sim-tools` image provides the Python runtime and external solvers required
by simulation gates. Mutable tags alone do not identify the exact environment
that produced a report.

## Decision

Publish `sim-tools` to GHCR with a commit-specific tag and `latest` alias. Run
the smoke checks against the pushed image, record its measured tools and
sha256 digest in `docker/image-digests.json`, and copy the same entry to
`plugins/sim/tools-image.json`. The launcher continues to use its existing
`auto`/`docker`/`host` selection rules.

The optional `sim-tools-em` image remains a reserved null-digest entry. Its
openEMS and CSXCAD components are source-built and are not published by this
workflow.

## Consequences

Published launcher references are immutable and auditable. Local build tags
are used only for verification and are never written to the committed digest
lock.
