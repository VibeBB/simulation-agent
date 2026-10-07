# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Reporting a vulnerability

Please do not open public issues for security vulnerabilities. Report them
via [GitHub private vulnerability reporting](https://github.com/VibeBB/simulation-agent/security/advisories/new)
on this repository, or by contacting the maintainer directly. Include:

- the affected version/commit,
- a minimal reproduction (brief JSON, command, or payload),
- impact assessment if known.

You can expect an acknowledgement within a few days. We will coordinate a
fix and disclosure with you before publishing details.

## Scope notes

sim executes contract validation, gate evaluation, and solver runs locally.
The `protect-generated` hook and fail-closed gates defend projection
integrity but are not a sandbox: do not run untrusted briefs or netlists in
environments where a crafted file could reach other tooling — ngspice,
CalculiX, and openEMS parse external simulation data as native code. The
MCP server speaks stdio only and never opens network listeners.

Secrets must never be written to logs, inputs, contracts, or commits; see
the invariants in [AGENTS.md](AGENTS.md).

## Repository hardening posture

OpenSSF Scorecard findings on branch protection (required approvers, code
owners, administrator binding) are intentional for this solo-maintainer
bot-merge workflow — merges are performed by automation and gated on the
required-check set rather than human approval. The full rationale is in
[docs/operations.md](docs/operations.md#settings-level-posture-recorded-decisions).
