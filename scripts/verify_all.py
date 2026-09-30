from __future__ import annotations

import argparse
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAST_COMMANDS = [
    ["uv", "sync", "--locked"],
    ["uv", "run", "ruff", "check", "."],
    ["uv", "run", "ruff", "format", "--check", "."],
    ["uv", "run", "pyright"],
    ["uv", "run", "pytest", "--cov", "--cov-report=term-missing:skip-covered"],
    ["uv", "run", "python", "scripts/check_shared_hooks.py"],
    ["uv", "run", "python", "scripts/verify_docs.py"],
    ["git", "diff", "--check", "HEAD^"],
]

STAGES = {
    "docs": [
        ["uv", "run", "python", "scripts/verify_docs.py"],
        ["git", "diff", "--check", "HEAD^"],
    ],
    "fast": FAST_COMMANDS,
    "standard": [
        *FAST_COMMANDS,
        ["uv", "run", "python", "scripts/check_plugin_load.py"],
        ["actionlint"],
        [
            "docker",
            "build",
            "--target",
            "sim-tools",
            "-f",
            "docker/sim-tools.Dockerfile",
            "-t",
            "sim-tools:verify",
            ".",
        ],
        ["uv", "run", "python", "scripts/smoke_image.py", "--image", "sim-tools:verify"],
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=tuple(STAGES), default="fast")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        for stage, commands in STAGES.items():
            print(f"{stage}:")
            for command in commands:
                print("  " + " ".join(command))
        return 0
    for command in STAGES[args.stage]:
        print("$ " + " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
