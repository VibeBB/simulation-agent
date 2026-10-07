# Hooks

Hooks are declared in `plugins/sim/hooks/hooks.json` and re-declared per
agent (plugin hooks do not propagate to subagents). Every command resolves
the plugin root from `SIM_PLUGIN_ROOT`, the workspace, or the installed
plugin dirs (`~/.agents/plugins/sim`, `~/.openhands/plugins/installed/sim`,
`${HOME}/plugins/installed/sim`, `${OH_PERSISTENCE_DIR}/plugins/installed/sim`),
and every hook except `protect-generated` exits 0 when the
plugin cannot be resolved. The two extra candidates resolve the plugin
inside an OpenHands docker conversation runtime (inner
`HOME=/var/openhands/.openhands`), where `sim_launcher.py` then fails
closed with guidance — docker is unavailable there by design.

Shared hooks (canonical across the sister repos; hash-compared by
`scripts/check_shared_hooks.py`): `_records.py`, `require_records.py`,
`intake_attachments.py` is repo-specific here, `_provenance.py` is shared
where present. Repo-specific scripts: `protect_generated.py`,
`record_image_observation.py`, `record_vision_tool_event.py`,
`report_sim_status.py`, `ux_inbox_notice.py`, plus the shared
`safety_rail.py`, `ensure_llm_profiles.py`, `ensure_agent_profiles.py`,
and `sim_launcher.py`-backed `sim-doctor`.

| Event | Hook | Matcher | Effect |
| --- | --- | --- | --- |
| session_start | sim-doctor | `*` | runs `doctor --warn`; advisory availability banner |
| session_start | intake-attachments | `*` | materializes attached images under `intake/attachments/` |
| session_start | ensure-llm-profiles | `*` | seeds `vibebb-author`/`vibebb-review`/`oracle` model profiles |
| session_start | ensure-agent-profiles | `*` | writes `~/.openhands/agent-profiles/vibebb-sim.json` when missing: openhands-kind, `llm_profile_ref=vibebb-author`, MCP scoped to `sim`, no secrets (shared canon) |
| session_start | ux-inbox-notice | `*` | lists pending SLP v2 requests + malformed count as `additionalContext` |
| session_start | require-records | `*` | session-start VRP state check |
| user_prompt_submit | intake-attachments | `*` | same intake pass per prompt |
| pre_tool_use | protect-generated | `file_editor\|apply_patch\|terminal` | denies writes to `out/`, `*.sim-response.json`, `liaison/*.ux-response.json`; exit 2 = block |
| pre_tool_use | safety-rail | `terminal` | blocks destructive commands |
| stop | require-records | `*` | Stop gate: blocks when owed VRP records are missing/malformed |
| stop | sim-report-status | `*` | appends a sim status line |
| stop | intake-attachments | `*` | final intake pass |
| post_tool_use | record-vision-tool-event | `inspect_image_with_vision` | records the vision answer under `observations/sim/` |
| post_tool_use | record-image-observation | `file_editor` + `sim_run`/`sim_gates`/`sim_respond`/`sim_plots`/`sim_<8 analyses>` | records that an image (plot PNG or attachment) was observed |

`scripts/check_shared_hooks.py` compares the shared scripts by normalized
AST hash against the canonical copies; `scripts/check_shared_workflows.py`
does the same for the 11 workflow copies.
