# Agents

The plugin declares three agents under `plugins/sim/agents/`. Plugin hooks
do not propagate to subagents, so each agent re-declares the hooks it needs
in its own frontmatter.

## sim-analyst — `vibebb-author` model

- Tools: `terminal`, `file_editor`, `grep`, `glob`, `task_tracker`,
  `VisionInspectTool`; the full `sim` MCP server.
- Budget: `max_iteration_per_run: 30`, `max_budget_per_run: 3.0`.
- Hooks: pre-tool `protect-generated` (file_editor|apply_patch|terminal) and
  `safety-rail` (terminal); post-tool `record-vision-tool-event`
  (`inspect_image_with_vision`) and `record-image-observation`
  (`file_editor` + every image-returning `sim_*` MCP tool).
- Duties: author strict `*.sim.json` briefs from explicit evidence, run
  deterministic gates via `sim run`, treat `unknown` as blocking, record
  decisions/impressions/vision reviews per the VRP protocol, and look at
  every plot with the matching checklist slug.

## sim-liaison — `vibebb-author` model

- Tools: same set as sim-analyst plus the `sim_ux_inbox`/`sim_ux_respond`
  MCP tools.
- Budget: `max_iteration_per_run: 30`, `max_budget_per_run: 3.0`.
- Hooks: identical pre/post-tool hook declaration.
- Duties: answer sister `*.sim-request.json` (v1 flow: rerun the requested
  analysis, write `*.sim-response.json` v2) and UX-creator SLP v2 requests
  under `liaison/` (states new/blocked/answered/stale; `done` needs hashed
  reports/artifacts, pass gate verdicts, and valid record refs).

## sim-review — `vibebb-review` model

- Tools: `terminal`, `file_editor`, `grep`, `glob`, `VisionInspectTool`
  (review-oriented, no `task_tracker`).
- Budget: `max_iteration_per_run: 30`, `max_budget_per_run: 3.0`.
- Hooks: identical pre/post-tool hook declaration.
- Duties: audit `out/<name>/` reports for evidence completeness, review
  every generated plot and sister render with `sim_record_vision_review`,
  flag stale inputs and unanswered liaison work; advisory only — it cannot
  promote or demote a deterministic verdict.
