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


def test_discover_tools_extracts_ngspice_version_banner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_which(binary: str) -> str | None:
        return "/usr/bin/ngspice" if binary == "ngspice" else None

    def fake_run(command: list[str] | str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "/usr/bin/ngspice":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="******\n** ngspice-36 : Circuit level simulator",
                stderr="",
            )
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="")

    monkeypatch.setattr("sim.tools.shutil.which", fake_which)
    monkeypatch.setattr("sim.tools.subprocess.run", fake_run)
    monkeypatch.setenv("SIM_NGSPICE", "ngspice")
    monkeypatch.setenv("SIM_RFSIM_RUNNER", str(tmp_path / "missing-runner.py"))

    tools = discover_tools()

    assert tools["ngspice"]["available"] is True
    assert tools["ngspice"]["version"] == "36"
    assert tools["ngspice"].get("detail") == "** ngspice-36 : Circuit level simulator"
