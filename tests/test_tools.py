from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sim.tools import discover_tools


def test_discover_tools_accepts_calculix_version_output_with_nonzero_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_version(binary: str, args: list[str]) -> tuple[bool, str | None, str | None]:
        if binary == "ccx":
            return False, "/usr/bin/ccx", "This is Version 2.17"
        return False, None, "binary not found"

    def fake_run(command: list[str] | str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="")

    monkeypatch.setattr("sim.tools._version", fake_version)
    monkeypatch.setattr("sim.tools.subprocess.run", fake_run)
    monkeypatch.setenv("SIM_RFSIM_RUNNER", str(tmp_path / "missing-runner.py"))

    tools = discover_tools()

    assert tools["ccx"]["available"] is True
    assert tools["ccx"]["version"] == "2.17"
