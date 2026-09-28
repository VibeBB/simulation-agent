"""External solver discovery and subprocess execution."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

TOOL_TIMEOUT_S = 10


def _version(binary: str, args: list[str]) -> tuple[bool, str | None, str | None]:
    path = shutil.which(binary)
    if path is None:
        return False, None, "binary not found"
    try:
        result = subprocess.run(
            [path, *args],
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, path, str(exc)
    output = (result.stdout + "\n" + result.stderr).strip()
    first = output.splitlines()[0] if output else f"exit {result.returncode}"
    return result.returncode == 0, path, first


def discover_tools() -> dict[str, Any]:
    ngspice = os.environ.get("SIM_NGSPICE", "ngspice")
    ccx = os.environ.get("SIM_CCX", "ccx")
    ng_ok, ng_path, ng_version = _version(ngspice, ["--version"])
    if not ng_ok:
        ng_ok, ng_path, ng_version = _version(ngspice, ["-v"])
    cc_ok, cc_path, cc_version = _version(ccx, ["-v"])
    openems_python = os.environ.get("SIM_OPENEMS_PYTHON", "python3")
    openems_ok, openems_path, openems_version = _version("openEMS", ["--help"])
    if not openems_ok:
        try:
            result = subprocess.run(
                [
                    openems_python,
                    "-c",
                    "import openEMS; print(getattr(openEMS, '__version__', 'available'))",
                ],
                capture_output=True,
                text=True,
                timeout=TOOL_TIMEOUT_S,
                check=False,
            )
            openems_ok = result.returncode == 0
            openems_path = openems_python if openems_ok else openems_path
            openems_version = (
                result.stdout.strip().splitlines()[0] if result.stdout.strip() else openems_version
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            openems_version = str(exc)
    runner = os.environ.get("SIM_RFSIM_RUNNER", "/opt/kicad-rfsim/plugins/runner.py")
    runner_path = Path(runner)
    return {
        "ngspice": {
            "available": ng_ok,
            "path": ng_path,
            "version": _extract_version(ng_version),
            "detail": ng_version,
        },
        "ccx": {
            "available": cc_ok,
            "path": cc_path,
            "version": _extract_version(cc_version),
            "detail": cc_version,
        },
        "openems": {
            "available": openems_ok,
            "path": openems_path,
            "python": openems_python,
            "version": openems_version,
        },
        "kicad_rfsim": {
            "available": runner_path.is_file(),
            "runner": str(runner_path),
            "version": None,
        },
    }


def _extract_version(value: str | None) -> str | None:
    if value is None:
        return None
    match = re.search(r"\d+(?:\.\d+)+", value)
    return match.group(0) if match else value
