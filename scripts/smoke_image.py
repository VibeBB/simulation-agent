from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]


def _run(
    docker: str, image: str, args: list[str], label: str
) -> tuple[subprocess.CompletedProcess[str], str]:
    workspace = str(ROOT)
    container = f"sim-smoke-{label}-{uuid.uuid4().hex[:12]}"
    result = subprocess.run(
        [
            docker,
            "run",
            "--name",
            container,
            "--network",
            "none",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            f"{workspace}:/workspace",
            "-w",
            "/workspace",
            "-e",
            "OPENHANDS_PROJECT_DIR=/workspace",
            "-e",
            "SIM_REQUIRED_TOOLS=ngspice,ccx",
            image,
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result, container


def _json_output(result: subprocess.CompletedProcess[str], label: str) -> dict[str, object]:
    if result.returncode != 0:
        raise RuntimeError(f"{label} exited {result.returncode}:\n{result.stdout}\n{result.stderr}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} did not emit JSON: {result.stdout!r}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} JSON output is not an object")
    mapping = cast(dict[object, object], value)
    output: dict[str, object] = {}
    for key, item in mapping.items():
        if not isinstance(key, str):
            raise RuntimeError(f"{label} JSON object has a non-string key")
        output[key] = item
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    args = parser.parse_args(argv)
    docker = shutil.which("docker")
    if docker is None:
        print("docker is not installed", file=sys.stderr)
        return 2
    try:
        doctor_result, doctor_container = _run(docker, args.image, ["doctor", "--strict"], "doctor")
        doctor = _json_output(
            doctor_result,
            "image doctor",
        )
        if doctor.get("missing"):
            raise RuntimeError(f"image doctor is missing required tools: {doctor['missing']}")
        report_result, example_container = _run(
            docker,
            args.image,
            ["gates", "examples/buck-regulator/buck.sim.json"],
            "example",
        )
        report = _json_output(
            report_result,
            "example gates",
        )
        if report.get("verdict") != "pass":
            raise RuntimeError(f"example verdict is {report.get('verdict')!r}")
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "Docker smoke passed: doctor strict and buck-regulator gates; "
        f"containers retained: {doctor_container}, {example_container}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
