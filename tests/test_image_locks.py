from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from scripts.measure_image_tools import measure
from scripts.print_locked_image import locked_image
from scripts.pull_locked_image import main as pull_main
from scripts.update_image_digest_lock import update_lock

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "docker" / "image-digests.json"
PLUGIN_LOCK = ROOT / "plugins" / "sim" / "tools-image.json"
NULL_LOCK = {
    "sim_tools": {
        "image": "ghcr.io/vibebb/sim-tools",
        "digest": None,
        "tag": None,
    },
    "sim_tools_em": {
        "image": "ghcr.io/vibebb/sim-tools-em",
        "digest": None,
        "tag": None,
    },
}


def test_sim_tools_lock_entry_has_valid_shape() -> None:
    entries = json.loads(LOCK.read_text(encoding="utf-8"))
    assert "sim_tools" in entries
    lock_entry = entries["sim_tools"]
    assert lock_entry["image"] == "ghcr.io/vibebb/sim-tools"
    if lock_entry["digest"] is None:
        assert lock_entry["tag"] is None
    else:
        assert isinstance(lock_entry["digest"], str)
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", lock_entry["digest"])
        assert isinstance(lock_entry["tag"], str) and lock_entry["tag"]

    if PLUGIN_LOCK.exists():
        plugin_entry = json.loads(PLUGIN_LOCK.read_text(encoding="utf-8"))
        assert {key: plugin_entry[key] for key in ("image", "digest", "tag")} == {
            key: lock_entry[key] for key in ("image", "digest", "tag")
        }
    else:
        assert lock_entry["digest"] is None and lock_entry["tag"] is None


def test_print_locked_image_requires_a_digest(tmp_path: Path) -> None:
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            {
                "sim_tools": {
                    "image": "ghcr.io/vibebb/sim-tools",
                    "digest": "sha256:" + "a" * 64,
                }
            }
        ),
        encoding="utf-8",
    )
    assert locked_image(lock, "sim_tools") == f"ghcr.io/vibebb/sim-tools@sha256:{'a' * 64}"
    null_lock = tmp_path / "null-lock.json"
    null_lock.write_text(json.dumps(NULL_LOCK), encoding="utf-8")
    with pytest.raises(ValueError, match="not digest-pinned"):
        locked_image(null_lock, "sim_tools")


def test_update_preserves_reserved_openems_entry(tmp_path: Path) -> None:
    lock = tmp_path / "image-digests.json"
    lock.write_text(json.dumps(NULL_LOCK), encoding="utf-8")
    changed = update_lock(
        lock,
        entry="sim_tools",
        image="ghcr.io/vibebb/sim-tools",
        tag="abc123-tools",
        digest="sha256:" + "b" * 64,
        published_at="2026-09-30T00:00:00Z",
        workflow_run="https://github.com/VibeBB/simulation-agent/actions/runs/1",
        dockerfile="docker/sim-tools.Dockerfile",
        tools={"python": "3.12", "ngspice": "45"},
        attestation="https://github.com/VibeBB/simulation-agent/attestations/1",
    )
    assert changed
    data = json.loads(lock.read_text(encoding="utf-8"))
    assert data["sim_tools"]["digest"] == "sha256:" + "b" * 64
    assert data["sim_tools"]["attestation"] == (
        "https://github.com/VibeBB/simulation-agent/attestations/1"
    )
    assert data["sim_tools_em"] == {
        "image": "ghcr.io/vibebb/sim-tools-em",
        "digest": None,
        "tag": None,
    }


def test_update_rejects_invalid_attestation_url(tmp_path: Path) -> None:
    lock = tmp_path / "image-digests.json"
    with pytest.raises(ValueError, match="attestation"):
        update_lock(
            lock,
            entry="sim_tools",
            image="ghcr.io/vibebb/sim-tools",
            tag="abc123-tools",
            digest="sha256:" + "b" * 64,
            published_at="2026-09-30T00:00:00Z",
            workflow_run="https://github.com/VibeBB/simulation-agent/actions/runs/1",
            dockerfile="docker/sim-tools.Dockerfile",
            tools={"python": "3.12"},
            attestation="http://invalid.example/attestation",
        )


def test_pull_locked_image_uses_the_digest_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            {
                "sim_tools": {
                    "image": "ghcr.io/vibebb/sim-tools",
                    "digest": "sha256:" + "c" * 64,
                    "attestation": "https://github.com/VibeBB/simulation-agent/attestations/1",
                }
            }
        ),
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def run(command: list[str], **_kwargs: object) -> Result:
        calls.append(command)
        return Result()

    monkeypatch.setattr("scripts.pull_locked_image.subprocess.run", run)
    record = tmp_path / "record.json"
    assert pull_main(["--lock", str(lock), "--entry", "sim_tools", "--record", str(record)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert calls == [["docker", "pull", "ghcr.io/vibebb/sim-tools@sha256:" + "c" * 64]]
    assert output["status"] == "pulled"
    assert json.loads(record.read_text(encoding="utf-8")) == output


def test_measure_records_probe_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        script = command[-1]
        assert "python --version" in script
        assert "uv --version" in script
        assert "ngspice --version" in script
        assert "dpkg-query -W" in script
        assert "import sim" in script
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                "Python 3.12.14\n"
                "uv 0.12.23\n"
                "** ngspice-45.2 : Circuit level simulation program\n"
                "ccx=2.21-1build1\n"
                "sim=0.1.0\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("scripts.measure_image_tools.subprocess.run", run)
    values = measure("sim-tools:local")
    assert values == {
        "ccx": "dpkg-query -W -f='${Version}\\n' calculix-ccx: 2.21-1build1",
        "ngspice": "ngspice --version: ** ngspice-45.2 : Circuit level simulation program",
        "python": "python --version: Python 3.12.14",
        "sim": "python -c 'import sim; print(sim.__version__)': 0.1.0",
        "uv": "uv --version: 0.12.23",
    }
