"""Run the canonical repository verification stages.

Commands run sequentially in declaration order. `--group`, `--match`, and
`--shard K/N` select subsets so CI can spread one stage across runner jobs
without duplicating the command list; barrier commands (setup) always run,
and a selection that matches no commands exits successfully.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GROUPS = ("lint", "unit", "docker")


@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]
    barrier: bool = False
    group: str | None = None


FAST_COMMANDS = [
    Command(("uv", "sync", "--locked"), barrier=True),
    Command(("uv", "run", "ruff", "check", "."), group="lint"),
    Command(("uv", "run", "ruff", "format", "--check", "."), group="lint"),
    Command(("uv", "run", "pyright"), group="lint"),
    Command(
        ("uv", "run", "pytest", "--cov", "--cov-report=term-missing:skip-covered"),
        group="unit",
    ),
    Command(("uv", "run", "python", "scripts/check_shared_hooks.py"), group="lint"),
    Command(("uv", "run", "python", "scripts/check_shared_workflows.py"), group="lint"),
    Command(("uv", "run", "python", "scripts/verify_docs.py"), group="lint"),
    Command(("git", "diff", "--check", "HEAD^"), group="lint"),
]

STAGES = {
    "docs": [
        Command(("uv", "run", "python", "scripts/verify_docs.py"), group="lint"),
        Command(("git", "diff", "--check", "HEAD^"), group="lint"),
    ],
    "fast": FAST_COMMANDS,
    "standard": [
        *FAST_COMMANDS,
        Command(("uv", "run", "python", "scripts/check_plugin_load.py"), group="lint"),
        Command(("actionlint",), group="lint"),
        Command(
            (
                "docker",
                "build",
                "--target",
                "sim-tools",
                "-f",
                "docker/sim-tools.Dockerfile",
                "-t",
                "sim-tools:verify",
                ".",
            ),
            group="docker",
        ),
        Command(
            ("uv", "run", "python", "scripts/smoke_image.py", "--image", "sim-tools:verify"),
            group="docker",
        ),
    ],
}


def _select(
    commands: list[Command],
    group: str | None,
    match: str | None,
    shard: str | None,
) -> list[Command]:
    if group is None and match is None and shard is None:
        return commands
    selected = [
        command
        for command in commands
        if command.barrier
        or (
            (group is None or command.group == group)
            and (match is None or match in " ".join(command.argv))
        )
    ]
    if shard is not None:
        shard_index_text, _, shard_count_text = shard.partition("/")
        shard_index = int(shard_index_text)
        shard_count = int(shard_count_text)
        if not 0 <= shard_index < shard_count:
            raise ValueError("--shard requires 0 <= K < N")
        non_barrier_positions = {
            id(command)
            for index, command in enumerate(c for c in selected if not c.barrier)
            if index % shard_count == shard_index
        }
        selected = [
            command
            for command in selected
            if command.barrier or id(command) in non_barrier_positions
        ]
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=tuple(STAGES), default="fast")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--group", choices=GROUPS, default=None)
    parser.add_argument(
        "--match",
        default=None,
        help="run only commands whose argv contains this substring",
    )
    parser.add_argument(
        "--shard",
        default=None,
        metavar="K/N",
        help="run the K-th slice (0-based) of the selected commands across N shards",
    )
    args = parser.parse_args()
    if args.list:
        print(
            json.dumps(
                {
                    stage: [
                        {
                            "command": list(command.argv),
                            "barrier": command.barrier,
                            "group": command.group,
                        }
                        for command in stage_commands
                    ]
                    for stage, stage_commands in STAGES.items()
                },
                indent=2,
            )
        )
        return 0
    try:
        commands = _select(STAGES[args.stage], args.group, args.match, args.shard)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    if not any(not command.barrier for command in commands):
        print("no commands matched the selection")
        return 0
    for command in commands:
        print("$ " + " ".join(command.argv), flush=True)
        result = subprocess.run(command.argv, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
