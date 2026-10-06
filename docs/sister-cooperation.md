# Sister cooperation

`sim` never imports a sister package; every exchange is a validated JSON
file in the shared workspace. Two protocols are in use.

## SLP v2 — UX-creator liaison

The ux-creator plugin directs multi-agent work by dropping
`<id>.ux-request.json` files into `liaison/`. `sim_ux_inbox` (CLI
`ux-inbox`) projects the directory into states:

- **new** — valid, addressed to `sim`, no response, dependencies answered
- **blocked** — a `depends_on` entry has no valid ux-response yet (any
  responder counts, not just `sim`)
- **answered** — a valid `<id>.ux-response.json` exists
- **stale** — answered, but a declared `inputs[]` hash no longer matches
- **malformed** — unparseable, or addressed to `sim` but schema-invalid
  (valid-looking requests for other targets are skipped silently)

`sim_ux_respond` writes the response. `done` additionally requires: hashed
`reports[]` or `artifacts[]`, only pass gate verdicts, matching declared
input hashes, ≥1 valid `decision_refs` and `impression_refs` (checked
against `valid_event_ids`), and all `depends_on` answered. `needs_info`
requires `questions[]`. Responses are written atomically and the
`protect-generated` hook blocks direct edits.

## v1 requests — `*.sim-request.json` / `*.sim-response.json`

Sisters send a `SimulationRequest` (`from_system`, `request_id`, `kind`,
`brief_path`, `question`). `sim respond` / `sim_respond` reruns the
requested analysis inside the workspace and writes a schema_version-2
`SimulationResponse`: `accepted` on deterministic pass, `rejected` on
fail, `needs_info` on unknown or missing evidence. The response binds
request and brief by sha256 and may carry validated `decision_refs`
(`--decision-ref`, repeatable).

## Interchange files per sister

| Sister | Inbound to sim | Outbound from sim |
| --- | --- | --- |
| circuit | connectivity/netlist exports, element ratings | margin + SPICE reports, request responses |
| mech | envelope/anchor data, material facts, `ruggedness` briefs + requests (`mech sim-request`) | FEM/thermal/ruggedness reports |
| wire | `WireContract` harness/connector data | EMC/DFT findings |
| ux-creator | SLP v2 `*.ux-request.json` | `*.ux-response.json`, report artifacts |
| bard / prodeng / doc / dashboard | v1 `*.sim-request.json`, summaries | `*.sim-response.json`, plots |
| firmware / fpga | v1 requests | responses |

Sister exports could eventually carry their own sha256 manifests; today
sim hashes every import and input itself on read.
