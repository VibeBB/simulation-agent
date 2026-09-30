# ADR-0006: Docker-only launcher default

- Status: Accepted
- Date: 2026-09-30

## Context

Running analyses with the host environment can silently use a different solver
set than the published `sim-tools` image.

## Decision

The launcher defaults to Docker and requires both the Docker executable and a
resolvable tools image. Missing requirements fail closed; `SIM_LAUNCH_MODE=host`
explicitly opts into host execution, while `auto` retains the prior
Docker-when-available behavior.

## Consequences

Plugin commands use the locked tools image by default. Developers without
Docker or an image can select host mode explicitly, and warning-mode hooks
continue to emit their existing non-blocking `unknown` result.
