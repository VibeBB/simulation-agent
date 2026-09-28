#!/usr/bin/env python3
"""Resolve simulation source and run the CLI or MCP server on host or Docker."""

from __future__ import annotations

import json
import os
import pwd
import shutil
import sys
from pathlib import Path

MODULES = {"mcp_server": "sim.mcp_server"}
CONTAINER_SRC = "/plugin-src"
PASSTHROUGH_ENV = {
    "OPENHANDS_PROJECT_DIR",
    "SIM_NGSPICE",
    "SIM_CCX",
    "SIM_OPENEMS_PYTHON",
    "SIM_RFSIM_RUNNER",
    "SIM_REQUIRED_TOOLS",
}


def _homes() -> list[Path]:
    homes = [Path.home()]
    try:
        real = Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError):
        return homes
    if real not in homes:
        homes.append(real)
    return homes


def _source_candidates(plugin_root: Path) -> list[Path]:
    candidates: list[Path] = []
    if os.environ.get("SIM_SRC"):
        candidates.append(Path(os.environ["SIM_SRC"]))
    for home in _homes():
        cache = home / ".openhands" / "cache" / "extensions"
        if cache.is_dir():
            try:
                candidates.extend(
                    sorted(
                        cache.glob("simulation-agent-*/src"),
                        key=lambda item: item.stat().st_mtime,
                        reverse=True,
                    )
                )
            except OSError:
                continue
    candidates.append(plugin_root.parent.parent / "src")
    return candidates


def resolve_source(plugin_root: Path) -> Path | None:
    for candidate in _source_candidates(plugin_root):
        try:
            if (candidate / "sim" / "__init__.py").is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _image_ref(plugin_root: Path) -> str | None:
    env_ref = os.environ.get("SIM_TOOLS_IMAGE")
    if env_ref:
        return env_ref
    paths = [
        plugin_root / "tools-image.json",
        plugin_root.parent.parent / "docker" / "image-digests.json",
    ]
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entry = value.get("sim_tools") if path.name == "image-digests.json" else value
        if not isinstance(entry, dict) or not isinstance(entry.get("image"), str):
            continue
        if entry.get("digest"):
            return f"{entry['image']}@{entry['digest']}"
        if entry.get("tag"):
            return f"{entry['image']}:{entry['tag']}"
    return None


def _docker_argv(docker: str, image: str, source: Path | None, argv: list[str]) -> list[str]:
    workspace = Path(os.environ.get("OPENHANDS_PROJECT_DIR") or Path.cwd()).resolve()
    command = [
        docker,
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-v",
        f"{workspace}:{workspace}",
        "-w",
        str(workspace),
    ]
    if source is not None:
        command += ["-v", f"{source}:{CONTAINER_SRC}:ro", "-e", f"PYTHONPATH={CONTAINER_SRC}"]
    for key in PASSTHROUGH_ENV:
        if key in os.environ:
            command += ["-e", f"{key}={os.environ[key]}"]
    command += [
        "-e",
        "HOME=/tmp",
        "-e",
        "TMPDIR=/tmp",
        image,
        *argv,
    ]
    return command


def _host_command(source: Path | None, argv: list[str]) -> list[str]:
    env_source = dict(os.environ)
    if source is not None:
        existing = env_source.get("PYTHONPATH")
        env_source["PYTHONPATH"] = str(source) + (os.pathsep + existing if existing else "")
    os.environ.update(env_source)
    if argv and argv[0] in MODULES:
        return [sys.executable, "-m", MODULES[argv[0]], *argv[1:]]
    return [sys.executable, "-m", "sim", *argv]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: sim_launcher.py {mcp_server|doctor|<sim cli args...>}", file=sys.stderr)
        return 2
    plugin_root = Path(__file__).resolve().parents[1]
    source = resolve_source(plugin_root)
    mode = os.environ.get("SIM_LAUNCH_MODE", "auto")
    if mode not in {"auto", "docker", "host"}:
        print(f"SIM_LAUNCH_MODE must be auto, docker, or host (got {mode!r})", file=sys.stderr)
        return 2
    docker = shutil.which("docker")
    image = _image_ref(plugin_root)
    use_docker = mode == "docker" or (mode == "auto" and docker is not None and image is not None)
    if use_docker:
        if docker is None or image is None:
            message = "Docker mode requires docker and a resolvable SIM_TOOLS_IMAGE"
            if "--warn" in args:
                print(json.dumps({"verdict": "unknown", "warning": message}))
                return 0
            print(f"sim_launcher: {message}", file=sys.stderr)
            return 1
        inner = (
            ["python", "-m", MODULES[args[0]], *args[1:]]
            if args[0] in MODULES
            else [
                "python",
                "-m",
                "sim",
                *args,
            ]
        )
        os.execvpe(docker, _docker_argv(docker, image, source, inner), os.environ)
    if source is None:
        print("sim_launcher: simulation-agent source not found", file=sys.stderr)
        return 1
    if "--warn" in args:
        args.remove("--warn")
        args.append("--warn")
    command = _host_command(source, args)
    os.execvpe(command[0], command, os.environ)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
