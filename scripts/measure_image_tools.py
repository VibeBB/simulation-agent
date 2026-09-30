#!/usr/bin/env python3
"""Measure the runtime metadata required by the image digest lock."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

_IMAGE_REF = re.compile(r"[^@\s]+@sha256:[0-9a-f]{64}\Z")
_LOCAL_IMAGE_REF = re.compile(r"[a-z0-9][a-z0-9_.-]*:[a-z0-9][a-z0-9_.-]*\Z")


def measure(image_ref: str) -> dict[str, str]:
    if _IMAGE_REF.fullmatch(image_ref) is None and _LOCAL_IMAGE_REF.fullmatch(image_ref) is None:
        raise ValueError("image ref must be digest-pinned or a local tag")
    script = (
        "set -eu; "
        "python --version; "
        "uv --version; "
        "ngspice --version 2>&1 | sed -n '2p'; "
        "printf 'ccx='; dpkg-query -W -f='${Version}\\n' calculix-ccx; "
        "python -c 'import sim; print(\"sim=\" + sim.__version__)'"
    )
    result = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "", image_ref, "sh", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "metadata probe failed")
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("Python "):
            values["python"] = f"python --version: {line}"
        elif line.startswith("uv "):
            values["uv"] = f"uv --version: {line.removeprefix('uv ')}"
        elif "ngspice-" in line:
            values["ngspice"] = f"ngspice --version: {line}"
        elif line.startswith("ccx="):
            values["ccx"] = (
                f"dpkg-query -W -f='${{Version}}\\n' calculix-ccx: {line.removeprefix('ccx=')}"
            )
        elif line.startswith("sim="):
            values["sim"] = (
                f"python -c 'import sim; print(sim.__version__)': {line.removeprefix('sim=')}"
            )
    required = {"python", "uv", "ngspice", "ccx", "sim"}
    if required - values.keys():
        raise ValueError(f"metadata probe omitted: {sorted(required - values.keys())}")
    return dict(sorted(values.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = measure(args.image_ref)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError, RuntimeError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"WROTE {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
