# ADR-0008: Docker-only launcher, no host mode

- Status: Accepted
- Date: 2026-10-05
- Supersedes: the `SIM_LAUNCH_MODE=host|auto` escape hatch of ADR-0006

## Context

ADR-0006 made Docker the default but kept `SIM_LAUNCH_MODE=host` and `auto`
fallbacks. Host execution silently bypasses the pinned solver set and can
produce results that differ from the published `sim-tools` image while
looking identical in the report.

## Decision

`plugins/sim/scripts/sim_launcher.py` runs plugin commands only inside the
pinned `sim-tools` image. `SIM_LAUNCH_MODE` unset or `docker` selects the
Docker path; any other value exits 2. Missing Docker or an unresolvable
image keeps the existing fail-closed behavior: exit 1 with a hint to
install Docker, run `sim_launcher.py prewarm`, or set `SIM_TOOLS_IMAGE`;
`--warn` still emits a non-blocking `unknown` JSON.

## Consequences

Every plugin invocation uses the same locked tool versions. Developers
without Docker cannot run plugin commands at all; host runs remain possible
only outside the plugin boundary (`python -m sim` from a source checkout).
