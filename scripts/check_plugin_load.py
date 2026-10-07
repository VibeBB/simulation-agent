from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins" / "sim"
EXPECTED_AGENTS = {"sim-analyst", "sim-liaison", "sim-review"}
EXPECTED_SKILLS = {
    "sim-brief",
    "sim-brief-rules",
    "sim-dft",
    "sim-emc-esd",
    "sim-fem-calculix",
    "sim-pdn-thermal",
    "sim-rf-openems",
    "sim-out-rules",
    "sim-sibling-cooperation",
    "sim-spice",
    "sim-vision-review",
    "sim-wca",
    "sim-workflow",
}
EXPECTED_COMMANDS = {
    "doctor",
    "run",
    "spice",
    "pdn",
    "thermal",
    "wca",
    "emc",
    "dft",
    "fem",
    "rf",
    "ruggedness",
    "lifetime",
    "gates",
    "import",
    "respond",
    "records",
    "ux-inbox",
    "plots",
}
EXPECTED_HOOKS = {
    "session_start": {
        "sim-doctor",
        "intake-attachments",
        "ensure-llm-profiles",
        "ensure-agent-profiles",
        "require-records",
        "ux-inbox-notice",
    },
    "user_prompt_submit": {"intake-attachments"},
    "pre_tool_use": {"protect-generated", "safety-rail"},
    "stop": {"require-records", "sim-report-status", "intake-attachments"},
    "post_tool_use": {"record-image-observation", "record-vision-tool-event"},
}


def _registered_tools() -> set[str]:
    import openhands.tools.preset.default  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
    from openhands.sdk.tool.registry import (  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
        list_registered_tools,
    )

    openhands.tools.preset.default.register_default_tools(enable_browser=False)
    import openhands.tools.glob.definition  # pyright: ignore[reportMissingImports,reportMissingModuleSource,reportUnusedImport]
    import openhands.tools.grep.definition  # pyright: ignore[reportMissingImports,reportMissingModuleSource,reportUnusedImport]
    import openhands.tools.task.definition  # pyright: ignore[reportMissingImports,reportMissingModuleSource,reportUnusedImport]
    from openhands.sdk.tool.builtins import (  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
        BUILT_IN_TOOL_CLASSES,
    )

    return set(list_registered_tools()) | set(BUILT_IN_TOOL_CLASSES)


def check_plugin(plugin_dir: Path = PLUGIN_DIR) -> list[str]:
    from openhands.sdk.plugin import (  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
        Plugin,
    )

    failures: list[str] = []
    try:
        plugin = Plugin.load(plugin_dir)
    except Exception as exc:
        return [f"Plugin.load failed: {exc}"]
    manifest = json.loads((plugin_dir / ".plugin" / "plugin.json").read_text(encoding="utf-8"))
    if plugin.manifest.version != manifest.get("version"):
        failures.append("SDK plugin manifest version does not match plugin.json")
    inventories = {
        "agents": ({agent.name for agent in plugin.agents}, EXPECTED_AGENTS),
        "skills": ({skill.name for skill in plugin.skills}, EXPECTED_SKILLS),
        "commands": ({command.name for command in plugin.commands}, EXPECTED_COMMANDS),
    }
    for label, (actual, expected) in inventories.items():
        if actual != expected:
            failures.append(f"{label}: {sorted(actual)} != {sorted(expected)}")
    if plugin.hooks is None:
        failures.append("plugin hooks were not loaded")
    else:
        for event, expected in EXPECTED_HOOKS.items():
            groups: list[Any] = getattr(plugin.hooks, event, None) or []
            actual = {
                hook.name for group in groups for hook in group.hooks if hook.name is not None
            }
            if actual != expected:
                failures.append(f"{event} hooks: {sorted(actual)} != {sorted(expected)}")
    registered = _registered_tools()
    for agent in plugin.agents:
        for tool in agent.tools:
            if tool not in registered:
                failures.append(f"agent {agent.name} has unregistered tool {tool!r}")
    for command in plugin.commands:
        for tool in command.allowed_tools:
            if tool not in registered:
                failures.append(f"command {command.name} has unregistered tool {tool!r}")
    return failures


def main() -> int:
    failures = check_plugin()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(
        "plugin-load OK: 3 agents, 18 commands, 13 skills, "
        "session-start/user-prompt-submit/pre-tool-use/stop/post-tool-use hooks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
