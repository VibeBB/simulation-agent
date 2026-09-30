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
