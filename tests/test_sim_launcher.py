from __future__ import annotations

import importlib.util
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypedDict

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = ROOT / "plugins" / "sim" / "scripts" / "sim_launcher.py"
SPEC = importlib.util.spec_from_file_location("sim_launcher", LAUNCHER_PATH)
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class ImagePinFixture(TypedDict):
    ref: str
    image: str | None
    digest: str | None
    attestation: str | None


def _docker_path(_name: str) -> str:
    return "/usr/bin/docker"


def _no_docker(_name: str) -> None:
    return None


def _no_image(_root: Path) -> None:
    return None


def _test_image_pin(_root: Path) -> ImagePinFixture:
    return {
        "ref": "sim-tools:test",
        "image": None,
        "digest": None,
        "attestation": None,
    }


def _ensure_test_image(pin: ImagePinFixture, **_kwargs: bool) -> str:
    return pin["ref"]


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
    monkeypatch.setattr(launcher, "_image_pin", _no_image)
    calls = _capture_exec(monkeypatch)

    assert launcher.main(["doctor"]) == 1
    assert not calls
    error = capsys.readouterr().err
    assert "SIM_TOOLS_IMAGE" in error
    assert "prewarm" in error
    assert "SIM_LAUNCH_MODE=host" not in error


def test_default_docker_without_binary_fails_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setattr(launcher.shutil, "which", _no_docker)
    monkeypatch.setattr(launcher, "_image_pin", _test_image_pin)
    calls = _capture_exec(monkeypatch)

    assert launcher.main(["doctor"]) == 1
    assert not calls
    error = capsys.readouterr().err
    assert "docker is not on PATH" in error
    assert "SIM_LAUNCH_MODE=host" not in error


def test_default_docker_warn_emits_unknown_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setattr(launcher.shutil, "which", _no_docker)
    monkeypatch.setattr(launcher, "_image_pin", _no_image)
    calls = _capture_exec(monkeypatch)

    assert launcher.main(["doctor", "--warn"]) == 0
    assert not calls
    warning = json.loads(capsys.readouterr().out)
    assert warning["verdict"] == "unknown"
    assert "docker is not on PATH" in warning["warning"]
    assert "SIM_TOOLS_IMAGE" in warning["warning"]
    assert "SIM_LAUNCH_MODE=host" not in warning["warning"]


@pytest.mark.parametrize("mode", ["host", "auto", "invalid"])
def test_removed_launch_modes_exit_two(
    mode: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SIM_LAUNCH_MODE", mode)
    calls = _capture_exec(monkeypatch)

    assert launcher.main(["doctor"]) == 2
    assert not calls
    error = capsys.readouterr().err
    assert "host/auto were removed" in error
    assert "pinned sim-tools image" in error


def test_default_docker_runs_image_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setattr(launcher.shutil, "which", _docker_path)
    monkeypatch.setattr(launcher, "_image_pin", _test_image_pin)
    monkeypatch.setattr(launcher, "_ensure_image", _ensure_test_image)
    calls = _capture_exec(monkeypatch)

    assert launcher.main(["doctor"]) == 0
    executable, argv, _env = calls[0]
    assert executable == "/usr/bin/docker"
    assert argv[:2] == ["/usr/bin/docker", "run"]
    assert "sim-tools:test" in argv
    assert argv[-3:] == ["-m", "sim", "doctor"]
