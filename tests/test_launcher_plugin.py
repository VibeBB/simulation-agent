from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from sim.mcp_server import tool_specs

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = ROOT / "plugins" / "sim" / "scripts" / "sim_launcher.py"
SPEC = importlib.util.spec_from_file_location("sim_launcher", LAUNCHER_PATH)
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def test_launcher_resolves_repo_source() -> None:
    assert launcher.resolve_source(ROOT / "plugins" / "sim") == ROOT / "src"


def test_plugin_image_pin_precedes_repository_lock(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins" / "sim"
    plugin_root.mkdir(parents=True)
    plugin_pin = "sha256:" + "a" * 64
    (plugin_root / "tools-image.json").write_text(
        json.dumps(
            {
                "image": "ghcr.io/vibebb/sim-tools",
                "digest": plugin_pin,
                "attestation": "https://github.com/VibeBB/simulation-agent/attestations/1",
            }
        ),
        encoding="utf-8",
    )
    assert launcher._image_ref(plugin_root) == f"ghcr.io/vibebb/sim-tools@{plugin_pin}"


def test_null_plugin_pin_falls_back_to_sim_tools_lock(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins" / "sim"
    plugin_root.mkdir(parents=True)
    (plugin_root / "tools-image.json").write_text(
        json.dumps(
            {
                "image": "ghcr.io/vibebb/sim-tools",
                "digest": None,
                "tag": None,
            }
        ),
        encoding="utf-8",
    )
    lock_path = tmp_path / "docker" / "image-digests.json"
    lock_path.parent.mkdir()
    locked_digest = "sha256:" + "b" * 64
    lock_path.write_text(
        json.dumps(
            {
                "sim_tools": {
                    "image": "ghcr.io/vibebb/sim-tools",
                    "digest": locked_digest,
                    "tag": "abc-tools",
                },
                "sim_tools_em": {
                    "image": "ghcr.io/vibebb/sim-tools-em",
                    "digest": None,
                    "tag": None,
                },
            }
        ),
        encoding="utf-8",
    )
    assert launcher._image_ref(plugin_root) == f"ghcr.io/vibebb/sim-tools@{locked_digest}"


def test_docker_launcher_forwards_only_approved_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("SIM_NGSPICE", "/usr/bin/ngspice")
    monkeypatch.setenv("SIM_PRIVATE_TOKEN", "must-not-pass")
    monkeypatch.setenv("OPENHANDS_API_KEY", "must-not-pass")

    command = launcher._docker_argv(
        "docker", "sim-tools:test", ROOT / "src", ["python", "-m", "sim"]
    )

    assert "SIM_NGSPICE=/usr/bin/ngspice" in command
    assert all("must-not-pass" not in item for item in command)
    assert not any(item.startswith("SIM_PRIVATE_TOKEN=") for item in command)
    assert not any(item.startswith("OPENHANDS_API_KEY=") for item in command)


def test_plugin_assets_match_v01_inventory() -> None:
    plugin = ROOT / "plugins" / "sim"
    manifest = json.loads((plugin / ".plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "sim"
    assert {path.stem for path in (plugin / "agents").glob("*.md")} == {
        "sim-analyst",
        "sim-review",
        "sim-liaison",
    }
    assert len(list((plugin / "commands").glob("*.md"))) == 18
    assert len(list((plugin / "skills").glob("*/SKILL.md"))) == 11
    for agent in (plugin / "agents").glob("*.md"):
        header = agent.read_text(encoding="utf-8").split("---", 2)[1]
        assert "hooks:" in header
    for command in (plugin / "commands").glob("*.md"):
        text = command.read_text(encoding="utf-8")
        assert "plugins/sim/scripts/sim_launcher.py" in text
        command_name = command.stem
        cli_command = {
            "doctor": "doctor",
            "run": "run",
            "spice": "run",
            "pdn": "run",
            "thermal": "run",
            "wca": "run",
            "emc": "run",
            "dft": "run",
            "fem": "run",
            "rf": "run",
            "ruggedness": "run",
            "lifetime": "run",
            "gates": "gates",
            "import": "import",
            "respond": "respond",
            "records": "record",
            "ux-inbox": "ux-inbox",
            "plots": "plots",
        }[command_name]
        assert f"sim_launcher.py {cli_command}" in text
        if command_name in {
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
        }:
            assert f"--only {command_name}" in text
    assert {tool.name for tool in tool_specs()} >= {
        "sim_doctor",
        "sim_run",
        "sim_gates",
        "sim_import",
        "sim_respond",
        "sim_spice",
        "sim_pdn",
        "sim_thermal",
        "sim_wca",
        "sim_emc",
        "sim_dft",
        "sim_fem",
        "sim_rf",
    }


def _rootless_options(_docker: str) -> str:
    return '["name=seccomp,profile=builtin","name=rootless","name=cgroupns"]'


def _no_options(_docker: str) -> None:
    return None


def test_container_user_rootless(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rootless daemons get 0:0 — the host uid maps to an unusable subuid."""
    import os

    monkeypatch.setattr(launcher, "_docker_info_security_options", _rootless_options)
    assert launcher._container_user("docker") == "0:0"
    command = launcher._docker_argv("docker", "sim-tools:test", None, ["python", "-m", "sim"])
    assert command[command.index("--user") + 1] == "0:0"
    monkeypatch.setattr(launcher, "_docker_info_security_options", _no_options)
    assert launcher._container_user("docker") == f"{os.getuid()}:{os.getgid()}"


def test_smoke_image_container_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """scripts/smoke_image.py shares the same rootless rule."""
    import os
    import sys

    monkeypatch.setattr(sys, "path", [str(ROOT / "scripts"), *sys.path])
    spec = importlib.util.spec_from_file_location(
        "smoke_image_test", ROOT / "scripts" / "smoke_image.py"
    )
    assert spec is not None and spec.loader is not None
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    monkeypatch.setattr(smoke, "_docker_info_security_options", _rootless_options)
    assert smoke._container_user("docker") == "0:0"
    monkeypatch.setattr(smoke, "_docker_info_security_options", _no_options)
    assert smoke._container_user("docker") == f"{os.getuid()}:{os.getgid()}"
