from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _hook(path: str, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / path)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


def test_generated_outputs_are_protected(tmp_path: Path) -> None:
    result = _hook(
        "plugins/sim/hooks/scripts/protect_generated.py",
        {
            "working_dir": str(tmp_path),
            "tool_name": "file_editor",
            "tool_input": {"path": "out/board/sim-report.json"},
        },
    )

    assert result.returncode == 2
    assert "cannot be edited directly" in result.stderr


def test_generated_output_symlink_is_protected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "out").symlink_to(outside, target_is_directory=True)
    result = _hook(
        "plugins/sim/hooks/scripts/protect_generated.py",
        {
            "working_dir": str(tmp_path),
            "tool_name": "file_editor",
            "tool_input": {"path": "out/board/sim-report.json"},
        },
    )

    assert result.returncode == 2


def test_vision_artifacts_are_protected(tmp_path: Path) -> None:
    for path in (
        "observations/sim/image-observations.jsonl",
        "observations/sim/vision-tool-events.jsonl",
        "intake/attachments/manifest.jsonl",
    ):
        result = _hook(
            "plugins/sim/hooks/scripts/protect_generated.py",
            {
                "working_dir": str(tmp_path),
                "tool_name": "file_editor",
                "tool_input": {"command": "write", "path": path},
            },
        )
        assert result.returncode == 2, path


def test_vision_artifacts_are_protected_from_patch_and_terminal(tmp_path: Path) -> None:
    patch = _hook(
        "plugins/sim/hooks/scripts/protect_generated.py",
        {
            "working_dir": str(tmp_path),
            "tool_name": "apply_patch",
            "tool_input": {"patch": "+++ b/observations/sim/image-observations.jsonl\n"},
        },
    )
    terminal = _hook(
        "plugins/sim/hooks/scripts/protect_generated.py",
        {
            "working_dir": str(tmp_path),
            "tool_name": "terminal",
            "tool_input": {"command": "echo x > intake/attachments/manifest.jsonl"},
        },
    )

    assert patch.returncode == 2
    assert terminal.returncode == 2


def test_apply_patch_openhands_header_targets_vision_artifacts(tmp_path: Path) -> None:
    blocked = _hook(
        "plugins/sim/hooks/scripts/protect_generated.py",
        {
            "working_dir": str(tmp_path),
            "tool_name": "apply_patch",
            "tool_input": {"patch": "*** Update File: observations/sim/image-observations.jsonl\n"},
        },
    )
    allowed = _hook(
        "plugins/sim/hooks/scripts/protect_generated.py",
        {
            "working_dir": str(tmp_path),
            "tool_name": "apply_patch",
            "tool_input": {"patch": "*** Update File: briefs/x.sim.json\n"},
        },
    )

    assert blocked.returncode == 2
    assert allowed.returncode == 0


def test_record_logs_and_session_markers_are_protected(tmp_path: Path) -> None:
    for path in (
        "observations/sim/decisions.jsonl",
        "observations/sim/impressions.jsonl",
        "observations/sim/vision-reviews.jsonl",
        "observations/sim/records-status.json",
        "observations/sim/.sessions/s1.json",
    ):
        result = _hook(
            "plugins/sim/hooks/scripts/protect_generated.py",
            {
                "working_dir": str(tmp_path),
                "tool_name": "file_editor",
                "tool_input": {"command": "write", "path": path},
            },
        )
        assert result.returncode == 2, path


def test_plugin_and_agent_vision_hooks_are_declared() -> None:
    plugin_root = ROOT / "plugins" / "sim"
    hooks = json.loads((plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    expected = {
        "session_start": {
            "sim-doctor",
            "intake-attachments",
            "ensure-llm-profiles",
            "ensure-agent-profiles",
            "ux-inbox-notice",
            "require-records",
        },
        "user_prompt_submit": {"intake-attachments"},
        "stop": {"require-records", "sim-report-status", "intake-attachments"},
        "post_tool_use": {"record-image-observation", "record-vision-tool-event"},
    }
    for event, names in expected.items():
        actual = {hook["name"] for group in hooks[event] for hook in group["hooks"]}
        assert actual == names
    for name in ("sim-analyst", "sim-liaison", "sim-review"):
        text = (plugin_root / "agents" / f"{name}.md").read_text(encoding="utf-8")
        assert "name: record-image-observation" in text
        assert "name: record-vision-tool-event" in text


def test_safety_rail_denies_destructive_git_commands() -> None:
    result = _hook(
        "plugins/sim/hooks/scripts/safety_rail.py",
        {
            "tool_name": "terminal",
            "tool_input": {"command": "git reset --hard HEAD"},
        },
    )

    assert result.returncode == 2
    assert "git reset --hard is banned by the working agreement" in result.stderr


def test_safety_rail_denies_canonical_denylist() -> None:
    for command in (
        "rm -rf /",
        "rm -fr ~",
        "dd if=x of=/dev/sda",
        "mkfs.ext4 /dev/sda1",
        "shutdown now",
        "git push origin main",
        "git push --force origin feat",
        "git reset --hard",
        "git clean -fd",
        "git checkout -- src/sim/gates.py",
        "git stash drop",
        "git add .",
        "git add -A",
        "git add --all",
        "git commit --amend",
        "git commit --no-verify",
    ):
        result = _hook(
            "plugins/sim/hooks/scripts/safety_rail.py",
            {"tool_name": "terminal", "tool_input": {"command": command}},
        )
        assert result.returncode == 2, command


def test_safety_rail_allows_canonical_safe_commands() -> None:
    for command in (
        "rm -rf out/artifacts",
        "git push --force-with-lease origin feat",
        "git push origin feat",
        "git add src/sim/gates.py docs",
        "git commit -m message",
        "python -m sim gates",
        "echo hi > out.txt",
        "find . -name '*.svg'",
    ):
        result = _hook(
            "plugins/sim/hooks/scripts/safety_rail.py",
            {"tool_name": "terminal", "tool_input": {"command": command}},
        )
        assert result.returncode == 0, command
