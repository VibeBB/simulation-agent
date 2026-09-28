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


def test_safety_rail_denies_destructive_git_commands() -> None:
    result = _hook(
        "plugins/sim/hooks/scripts/safety_rail.py",
        {
            "tool_name": "terminal",
            "tool_input": {"command": "git reset --hard HEAD"},
        },
    )

    assert result.returncode == 2
    assert "git reset --hard is denied" in result.stderr
