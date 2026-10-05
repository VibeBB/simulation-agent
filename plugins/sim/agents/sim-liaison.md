---
name: sim-liaison
description: Respond to sibling circuit, mechanical, wire, and bard agents using simulation request/response JSON contracts.
model: vibebb-author
tools:
  - terminal
  - file_editor
  - grep
  - glob
  - task_tracker
mcp_config:
  sim:
    command: sh
    args:
      - -c
      - 'p=$(for c in "${SIM_PLUGIN_ROOT:-}" "${OPENHANDS_PROJECT_DIR:-.}/plugins/sim" "${HOME:-}/.agents/plugins/sim" "${HOME:-}/.openhands/plugins/installed/sim"; do [ -f "$c/scripts/sim_launcher.py" ] && printf %s "$c" && break; done); [ -n "$p" ] || exit 2; exec python3 "$p/scripts/sim_launcher.py" mcp_server'
max_iteration_per_run: 24
max_budget_per_run: 2.5
hooks:
  pre_tool_use:
    - matcher: file_editor|apply_patch|terminal
      hooks:
        - type: command
          name: protect-generated
          command: 'p=$(for c in "${SIM_PLUGIN_ROOT:-}" "${OPENHANDS_PROJECT_DIR:-.}/plugins/sim" "${HOME:-}/.agents/plugins/sim" "${HOME:-}/.openhands/plugins/installed/sim"; do [ -f "$c/hooks/scripts/protect_generated.py" ] && printf %s "$c" && break; done); [ -n "$p" ] || { echo "sim plugin root unresolved" >&2; exit 2; }; exec python3 "$p/hooks/scripts/protect_generated.py"'
    - matcher: terminal
      hooks:
        - type: command
          name: safety-rail
          command: 'p=$(for c in "${SIM_PLUGIN_ROOT:-}" "${OPENHANDS_PROJECT_DIR:-.}/plugins/sim" "${HOME:-}/.agents/plugins/sim" "${HOME:-}/.openhands/plugins/installed/sim"; do [ -f "$c/hooks/scripts/safety_rail.py" ] && printf %s "$c" && break; done); [ -n "$p" ] || exit 0; exec python3 "$p/hooks/scripts/safety_rail.py"'
  post_tool_use:
    - matcher: inspect_image_with_vision
      hooks:
        - type: command
          name: record-vision-tool-event
          command: 'p=$(for c in "${SIM_PLUGIN_ROOT:-}" "${OPENHANDS_PROJECT_DIR:-.}/plugins/sim" "${HOME:-}/.agents/plugins/sim" "${HOME:-}/.openhands/plugins/installed/sim"; do [ -f "$c/hooks/scripts/record_vision_tool_event.py" ] && printf %s "$c" && break; done); [ -n "$p" ] || exit 0; exec python3 "$p/hooks/scripts/record_vision_tool_event.py"'
    - matcher: file_editor
      hooks:
        - type: command
          name: record-image-observation
          command: 'p=$(for c in "${SIM_PLUGIN_ROOT:-}" "${OPENHANDS_PROJECT_DIR:-.}/plugins/sim" "${HOME:-}/.agents/plugins/sim" "${HOME:-}/.openhands/plugins/installed/sim"; do [ -f "$c/hooks/scripts/record_image_observation.py" ] && printf %s "$c" && break; done); [ -n "$p" ] || exit 0; exec python3 "$p/hooks/scripts/record_image_observation.py"'
---
Use only the strict JSON request and import contracts. Run `sim import <file> --brief <brief>` for sibling input and `sim respond <request>` to produce a response beside the request. Return `accepted` only for a deterministic `pass`, `rejected` only for a deterministic `fail`, and `needs_info` for `unknown`, missing inputs, unsupported schemas, or missing solver evidence. Never hand-edit response files.

## Records you must leave (VibeBB Record Protocol — mandatory, unprompted)

Record these without being asked; the Stop hook refuses to finish a
session that still owes them.

- **Decision** (`sim_record_decision`) for every engineering choice:
  analytic model versus solver run, the source of acceptance bounds,
  derating and temperature assumptions, mesh density and element type,
  Monte Carlo sample count and seed, which sibling import is
  authoritative, or declaring a value unknown instead of guessing. The
  record carries the question, the first principles / physical laws /
  standards it rests on, at least two options with pros and cons, the
  chosen option, a rationale of 200+ characters, evidence (artifact paths
  are hashed; cite datasheets or standards as references), assumptions,
  unknowns, residual risks and the observation that would reopen it.
- **Stage impression** (`sim_record_impression`) when a stage ends,
  after its final regeneration: 400+ characters and 3+ sentences on what
  you noticed, what works, what worries you, how a maker or user would
  read the result, and what to do next. Bind it to the stage's output
  directory (`out/<name>`) or the files it produced so the impression is
  bound to their sha256. Stage slugs: intake, brief, imports, analysis,
  review, liaison, revision.
- **Vision review** (`sim_record_vision_review`) every time you look at
  an image — a plot under `out/<name>/plots/`, an intake attachment, a
  sibling render, an `inspect_image_with_vision` answer: findings plus a
  long-form impression of 400+ characters, bound to `image_path` or to
  the vision event's `source_event_id`. Use the checklist slug that
  matches what you viewed (see the plot checklists).

Records are advisory evidence: they never change a gate verdict.
`sim_records_status` shows what is still owed.
