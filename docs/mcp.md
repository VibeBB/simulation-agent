# MCP tools

`src/sim/mcp_server.py` serves the `sim` tool set over stdio (started via
`sim_launcher.py mcp_server` inside the tools image). Every tool returns
`TextContent` JSON; image-capable tools also append up to
`MAX_PLOT_IMAGES` (8) sha256-verified `ImageContent` PNGs — the JSON notes
`plot_hash_mismatches` and `plots_omitted` when that happens.

| Tool | Inputs | Writes | Notes |
| --- | --- | --- | --- |
| `sim_doctor` | none | nothing | tool/solver availability report |
| `sim_validate_brief` | `brief` | nothing | validates a `*.sim.json` |
| `sim_run` | `brief` (path) | `out/<name>/` | runs all declared analyses; returns report + inline plots |
| `sim_gates` | `brief` | nothing | gate summary without running |
| `sim_import` | `file`, `brief` | `imports[]`, `imports.json` | mirrors a sister contract |
| `sim_respond` | `request`, `decision_refs?` | `*.sim-response.json` | v1 flow; reruns the requested analysis |
| `sim_schema` | none | nothing | brief JSON schema |
| `sim_spice` … `sim_lifetime` | `brief` (path) | `out/<name>/` | one analysis each (10 tools); inline plots |
| `sim_plots` | `out_dir` | nothing | returns the report's plot list + inline PNGs |
| `sim_record_decision` | `DecisionInput` | `observations/sim/decisions.jsonl` | appends a validated VRP record |
| `sim_record_impression` | `StageImpressionInput` | `observations/sim/impressions.jsonl` | long-form stage impression |
| `sim_record_vision_review` | `VisionReviewInput` | `observations/sim/vision-reviews.jsonl` | checklist findings + impression |
| `sim_records_status` | none | nothing | record coverage/malformed counts |
| `sim_ux_inbox` | none | nothing | SLP v2 inbox states + malformed list |
| `sim_ux_respond` | ux-response JSON | `liaison/<id>.ux-response.json` | enforces done/needs_info rules |

Errors: invalid inputs raise a `ValueError` surfaced as a tool error;
missing files/tools produce `unknown` verdicts or explicit refusal strings,
never a pass. Read-only tools (`sim_doctor`, `sim_validate_brief`,
`sim_gates`, `sim_schema`, `sim_plots`, `sim_records_status`,
`sim_ux_inbox`) write nothing.
