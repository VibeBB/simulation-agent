---
name: sim-review
description: Review simulation reports for evidence completeness, assumptions, and unresolved gates.
model: vibebb-review
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
---
Review the generated report and its provenance. Distinguish measured solver output from analytic estimates and rule checks. Confirm missing tools, unexecuted checks, absent expected outputs, and unresolved sibling imports remain `unknown`. Do not promote narrative observations to deterministic verdicts.
