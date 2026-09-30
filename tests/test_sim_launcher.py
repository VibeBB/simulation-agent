from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = ROOT / "plugins" / "sim" / "scripts" / "sim_launcher.py"
SPEC = importlib.util.spec_from_file_location("sim_launcher", LAUNCHER_PATH)
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def _docker_path(_name: str) -> str:
    return "/usr/bin/docker"


def _no_docker(_name: str) -> None:
    return None


def _no_image(_root: Path) -> None:
    return None


def _test_image(_root: Path) -> str:
    return "sim-tools:test"


def _clear_launch_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIM_LAUNCH_MODE", raising=False)
    monkeypatch.delenv("SIM_TOOLS_IMAGE", raising=False)


def _capture_exec(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, list[str], Mapping[str, str]]]:
    calls: list[tuple[str, list[str], Mapping[str, str]]] = []

    def record(file: str, argv: Sequence[str], env: Mapping[str, str]) -> None:
        calls.append((file, list(argv), env))

    monkeypatch.setattr(launcher.os, "execvpe", record)
    return calls


def test_default_docker_without_image_fails_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setattr(launcher.shutil, "which", _docker_path)
    monkeypatch.setattr(launcher, "_image_ref", _no_image)
    calls = _capture_exec(monkeypatch)

    assert launcher.main(["doctor"]) == 1
    assert not calls
    error = capsys.readouterr().err
    assert "SIM_TOOLS_IMAGE" in error
    assert "SIM_LAUNCH_MODE=host" in error


def test_default_docker_without_binary_fails_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setattr(launcher.shutil, "which", _no_docker)
    monkeypatch.setattr(launcher, "_image_ref", _test_image)
    calls = _capture_exec(monkeypatch)

    assert launcher.main(["doctor"]) == 1
    assert not calls
    error = capsys.readouterr().err
    assert "docker is not on PATH" in error
    assert "SIM_LAUNCH_MODE=host" in error


def test_default_docker_warn_emits_unknown_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setattr(launcher.shutil, "which", _no_docker)
    monkeypatch.setattr(launcher, "_image_ref", _no_image)
    calls = _capture_exec(monkeypatch)

    assert launcher.main(["doctor", "--warn"]) == 0
    assert not calls
    warning = json.loads(capsys.readouterr().out)
    assert warning["verdict"] == "unknown"
    assert "docker is not on PATH" in warning["warning"]
    assert "SIM_TOOLS_IMAGE" in warning["warning"]
    assert "SIM_LAUNCH_MODE=host" in warning["warning"]


def test_host_mode_runs_on_host_when_image_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIM_LAUNCH_MODE", "host")
    monkeypatch.setenv("SIM_TOOLS_IMAGE", "sim-tools:test")
    monkeypatch.setattr(launcher.shutil, "which", _docker_path)
    monkeypatch.setattr(launcher, "_image_ref", _test_image)
    calls = _capture_exec(monkeypatch)

    assert launcher.main(["doctor"]) == 0
    assert calls[0][0] == sys.executable
    assert calls[0][1][:3] == [sys.executable, "-m", "sim"]


def test_auto_mode_without_image_falls_back_to_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIM_LAUNCH_MODE", "auto")
    monkeypatch.delenv("SIM_TOOLS_IMAGE", raising=False)
    monkeypatch.setattr(launcher.shutil, "which", _docker_path)
    monkeypatch.setattr(launcher, "_image_ref", _no_image)
    calls = _capture_exec(monkeypatch)

    assert launcher.main(["doctor"]) == 0
    assert calls[0][0] == sys.executable
    assert calls[0][1][:3] == [sys.executable, "-m", "sim"]


def test_invalid_mode_exits_two_with_usage(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SIM_LAUNCH_MODE", "invalid")
    calls = _capture_exec(monkeypatch)

    assert launcher.main(["doctor"]) == 2
    assert not calls
    assert "usage:" in capsys.readouterr().err


def test_default_docker_runs_image_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setattr(launcher.shutil, "which", _docker_path)
    monkeypatch.setattr(launcher, "_image_ref", _test_image)
    calls = _capture_exec(monkeypatch)

    assert launcher.main(["doctor"]) == 0
    executable, argv, _env = calls[0]
    assert executable == "/usr/bin/docker"
    assert argv[:2] == ["/usr/bin/docker", "run"]
    assert "sim-tools:test" in argv
    assert argv[-4:] == ["python", "-m", "sim", "doctor"]
