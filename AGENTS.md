# simulation-agent working agreement

`simulation-agent` is the deterministic engineering-analysis sister of the
circuit, mechanical, wire, UX, and bard agents. Its brief schema in
`src/sim/brief.py` and import mirrors in `src/sim/imports.py` are contract
sources of truth.

## Invariants

- Python 3.12+, package `src/sim/`, uv `0.12.23`, hatchling, Pydantic v2, and
  MCP. Runtime dependencies are limited to `pydantic>=2` and `mcp>=1.29,<2`.
- All contracts are frozen and reject extra fields. Missing facts, tools,
  outputs, parse results, or acceptance bounds remain `unknown`.
- Only deterministic Python gates emit `pass`, `fail`, or `unknown`. Agent
  commentary is advisory and cannot promote a result.
- Inter-agent exchange is through validated JSON files in the shared workspace.
  Never import a sister Python package. VRP v1 records (`observations/sim/`),
  SLP v2 liaison (`liaison/`), and deterministic PNG plots plus vision reviews
  follow the family's shared record protocol.
- Keep paths inside the workspace; never log or commit secrets.
- Shared hooks are canonical across the family; change all 11 copies together
  and update `EXPECTED` in `scripts/check_shared_hooks.py`. `_records.py`,
  `require_records.py`, and `_provenance.py` are shared where present; UX and
  Production Engineering intentionally omit `_provenance.py`.
  `intake_attachments.py`, `protect_generated.py`,
  `record_image_observation.py`, `record_vision_tool_event.py`,
  `report_sim_status.py`, and `ux_inbox_notice.py` are intentionally
  repo-specific.
- `out/` files, `*.sim-response.json` files, `liaison/*.ux-response.json`, and
  `observations/sim/*` are generated artifacts and cannot be edited directly.
  Fix inputs and regenerate them.
- The launcher is Docker-only (ADR-0008): plugin tools run inside the pinned
  `sim-tools` image; there is no host or auto mode.
- Copyleft solvers run as unmodified separate processes. Never link solver
  libraries or import-bind solver code.
- Code, docs, identifiers, and commit messages are in English.

## Layout

```text
src/sim/                 # schemas, deterministic checks, adapters, CLI, MCP
plugins/sim/              # OpenHands agents, commands, skills, hooks, launcher
tests/                    # contracts, analyses, adapters, plugin behavior
examples/buck-regulator/  # exercised multi-analysis example
docker/                   # sim-tools and optional sim-tools-em
scripts/                  # verification, docs, plugin-load, and smoke checks
docs/adr/                 # design decisions
```

Engineering guidance belongs in `plugins/sim/skills/`; the agents orchestrate
evidence gathering and the MCP server exposes deterministic entry points only.
Declare required hooks on each agent because plugin-level hooks do not
propagate to subagents.

## Verification

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
uv run python scripts/verify_all.py --stage fast
uv run python scripts/verify_all.py --stage standard
uv run python scripts/check_plugin_load.py
actionlint
```

Fast verification runs pytest through `scripts/structural_coverage.py run`;
coverage measures `src/sim` with branches and gates the C0, C1, decision,
C2, MC/DC and boundary floors in `pyproject.toml` (`docs/test-coverage.md`). `verify_all.py` also
accepts `--group` (lint/unit/docker), `--match`, and `--shard K/N` to run a
subset of a stage's commands so CI can spread one stage across jobs;
`--list` dumps the tagged command table.

Real-solver tests use the `tools` marker and skip only when the required
executable is absent. CI installs ngspice and CalculiX and therefore runs them.

## Git

Use focused commits with `feat(scope): summary` (72 characters maximum). Do
not amend, force-push, use `git add .`, skip hooks, or run destructive cleanup
commands. Keep the first research inventory unchanged.

Shared workflows are canonical across the family; change all 11 copies together and update `EXPECTED` in `scripts/check_shared_workflows.py`.

## CI/CD

Digest-lock PRs use `scripts/publish_image_pin_pr.sh`: the publisher
dispatches `ci.yml` and `workflow-lint.yml` on the lock branch, then polls
the authoritative required-check set for up to 15 minutes. Non-required
failures do not block publishing; a concluded required-check failure or a PR
closed without merge fails the job. A PR merged externally triggers the
existing post-merge main workflows. If required checks are still pending at
the deadline, the publisher arms squash auto-merge with branch deletion and
exits successfully.

The release bump-version state machine lives in `scripts/release_bump.sh`
(the workflow step is a thin wrapper) and is covered by
`tests/test_release_bump.py`, which exercises it against a stubbed `gh` and
local git remotes. `release.yml`'s `dry_run` input rehearses the release:
version arithmetic and tag checks run and downstream jobs still execute,
but nothing is committed, pushed, tagged, or released.

`publish-sim-images.yml` accepts a `dry_run` dispatch input that rehearses
the publish: the image is built into the local daemon (`push: false`,
`load: true`) and the Trivy gate, SBOM chain, measurement, and smoke checks
still run against the local tag, but nothing is pushed, `:latest` is not
promoted, no attestation is stored, the digest-lock PR is not opened, no
post-merge workflow is dispatched, and no SARIF reaches code scanning.

SPDX SBOM generation prefers registry pulls (the local daemon under
`dry_run`), uses runner temporary storage, and disables file metadata. The
attested SBOM is package-level SPDX 2.3; file entries and relationships
involving files are omitted to stay below 16 MiB. The full Syft SBOM is
attached to the workflow run as a 90-day artifact.

Steps that only run on main or dispatch are listed in
`docs/operations.md` under "Main-only verification boundary"; after merging
a workflow change that touches them, dispatch the affected workflow once
and verify the step in its run log.
