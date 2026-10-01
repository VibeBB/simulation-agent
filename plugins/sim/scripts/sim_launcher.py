#!/usr/bin/env python3
"""Resolve simulation source and run the CLI or MCP server on host or Docker.

Launcher-side verification uses SIM_VERIFY_ATTESTATION=auto|require|off.
It verifies lock provenance before pulls and on every prewarm; normal use
does not re-verify an image that is already present locally.
"""

from __future__ import annotations

import json
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, TypedDict, cast

MODULES = {"mcp_server": "sim.mcp_server"}
CONTAINER_SRC = "/plugin-src"
_INSPECT_TIMEOUT_S = 30
_PULL_TIMEOUT_S = 900
_ATTEST_TIMEOUT_S = 120
_GH_AUTH_TIMEOUT_S = 15
_VERIFY_ENV = "SIM_VERIFY_ATTESTATION"
_REPOSITORY = "VibeBB/simulation-agent"
_PUBLISH_FILE = ".github/workflows/publish-sim-images.yml"
PASSTHROUGH_ENV = {
    "OPENHANDS_PROJECT_DIR",
    "SIM_NGSPICE",
    "SIM_CCX",
    "SIM_OPENEMS_PYTHON",
    "SIM_RFSIM_RUNNER",
    "SIM_REQUIRED_TOOLS",
}


class ImagePin(TypedDict):
    ref: str
    image: str | None
    digest: str | None
    attestation: str | None


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


def _image_pin(plugin_root: Path) -> ImagePin | None:
    env_ref = os.environ.get("SIM_TOOLS_IMAGE")
    if env_ref:
        return {"ref": env_ref, "image": None, "digest": None, "attestation": None}
    paths = [
        plugin_root / "tools-image.json",
        plugin_root.parent.parent / "docker" / "image-digests.json",
    ]
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        value = cast(dict[str, Any], value)
        entry = value.get("sim_tools") if path.name == "image-digests.json" else value
        if not isinstance(entry, dict):
            continue
        entry = cast(dict[str, Any], entry)
        image = entry.get("image")
        if not isinstance(image, str) or not image:
            continue
        digest = entry.get("digest")
        digest = digest if isinstance(digest, str) and digest else None
        tag = entry.get("tag")
        tag = tag if isinstance(tag, str) and tag else None
        if digest is None and tag is None:
            continue
        attestation = entry.get("attestation")
        return {
            "ref": f"{image}@{digest}" if digest else f"{image}:{tag}",
            "image": image,
            "digest": digest,
            "attestation": attestation if isinstance(attestation, str) and attestation else None,
        }
    return None


def _image_ref(plugin_root: Path) -> str | None:  # pyright: ignore[reportUnusedFunction]
    pin = _image_pin(plugin_root)
    return pin["ref"] if pin is not None else None


def _attestation_mode() -> str:
    mode = os.environ.get(_VERIFY_ENV, "auto")
    if mode not in {"auto", "require", "off"}:
        raise ValueError(
            f"{_VERIFY_ENV} must be auto, require, or off (got {mode!r}); "
            f"usage: {_VERIFY_ENV}=auto|require|off"
        )
    return mode


def _run_timed(
    command: list[str],
    operation: str,
    timeout: int,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    try:
        return cast(
            subprocess.CompletedProcess[str],
            subprocess.run(command, timeout=timeout, **kwargs),
        )
    except OSError as exc:
        raise RuntimeError(f"{operation} failed: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{operation} timed out after {timeout}s") from exc


def _verify_attestation(pin: ImagePin, *, override: bool) -> None:
    mode = _attestation_mode()
    if mode == "off":
        return
    reason: str | None = None
    gh = shutil.which("gh")
    if override:
        reason = "tools image override has no lock attestation context"
    elif not pin["attestation"]:
        reason = "lock entry has no attestation"
    elif not pin["image"] or not pin["digest"]:
        reason = "lock entry has no digest"
    elif gh is None:
        reason = "gh is not on PATH"
    else:
        try:
            auth = _run_timed(
                [gh, "auth", "status"],
                "gh auth status",
                _GH_AUTH_TIMEOUT_S,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except RuntimeError:
            reason = "gh auth status failed"
        else:
            if auth.returncode != 0:
                reason = "gh auth status failed"
    if reason is not None:
        if mode == "require":
            raise RuntimeError(f"attestation verification required but {reason}")
        print(f"sim_launcher: attestation verification skipped: {reason}", file=sys.stderr)
        return
    assert gh is not None
    assert pin["image"] is not None and pin["digest"] is not None
    result = _run_timed(
        [
            gh,
            "attestation",
            "verify",
            f"oci://{pin['image']}@{pin['digest']}",
            "--repo",
            _REPOSITORY,
            "--signer-workflow",
            f"{_REPOSITORY}/{_PUBLISH_FILE}",
        ],
        "gh attestation verify",
        _ATTEST_TIMEOUT_S,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"attestation verification failed for {pin['image']}@{pin['digest']}")


def _ensure_image(
    pin: ImagePin,
    *,
    pull: bool,
    prewarm: bool = False,
    override: bool = False,
) -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker not found on PATH")
    ref = pin["ref"]
    if prewarm:
        _verify_attestation(pin, override=override)
    inspected = subprocess.run(
        [docker, "image", "inspect", ref],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=_INSPECT_TIMEOUT_S,
    )
    if inspected.returncode == 0:
        return ref
    if not pull:
        raise RuntimeError(f"sim tools image {ref} not pulled locally; run sim_launcher.py prewarm")
    if not prewarm:
        _verify_attestation(pin, override=override)
    pulled = subprocess.run(
        [docker, "pull", ref],
        stdout=subprocess.DEVNULL,
        check=False,
        timeout=_PULL_TIMEOUT_S,
    )
    if pulled.returncode != 0:
        raise RuntimeError(f"sim tools image {ref} not present locally and pull failed")
    return ref


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
        "--entrypoint",
        "python",
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
    try:
        _attestation_mode()
    except ValueError as exc:
        print(f"sim_launcher: {exc}", file=sys.stderr)
        return 2
    mode = os.environ.get("SIM_LAUNCH_MODE", "docker")
    if mode not in {"auto", "docker", "host"}:
        print(
            f"SIM_LAUNCH_MODE must be auto, docker, or host (got {mode!r}); "
            "usage: SIM_LAUNCH_MODE=auto|docker|host",
            file=sys.stderr,
        )
        return 2
    docker = shutil.which("docker")
    pin = _image_pin(plugin_root)
    image = pin["ref"] if pin is not None else None
    override = bool(os.environ.get("SIM_TOOLS_IMAGE"))
    if args[0] == "prewarm":
        if pin is None:
            message = "no simulation tools image is configured"
            if "--warn" in args:
                print(json.dumps({"verdict": "unknown", "warning": message}))
                return 0
            print(f"sim_launcher: {message}", file=sys.stderr)
            return 1
        try:
            image = _ensure_image(
                pin,
                pull="--warn" not in args,
                prewarm=True,
                override=override,
            )
        except RuntimeError as exc:
            if "--warn" in args:
                print(json.dumps({"verdict": "unknown", "warning": str(exc)}))
                return 0
            print(f"sim_launcher: {exc}", file=sys.stderr)
            return 1
        print(f"sim_launcher: tools image ready: {image}")
        return 0
    use_docker = mode == "docker" or (mode == "auto" and docker is not None and image is not None)
    if use_docker:
        if docker is None or pin is None or image is None:
            missing: list[str] = []
            if docker is None:
                missing.append("docker is not on PATH")
            if image is None:
                missing.append("no image resolved from SIM_TOOLS_IMAGE or the sim image lock")
            message = f"{'; '.join(missing)}. Set SIM_LAUNCH_MODE=host to run on the host."
            if "--warn" in args:
                print(json.dumps({"verdict": "unknown", "warning": message}))
                return 0
            print(f"sim_launcher: {message}", file=sys.stderr)
            return 1
        try:
            image = _ensure_image(
                pin,
                pull="--warn" not in args,
                override=override,
            )
        except RuntimeError as exc:
            if "--warn" in args:
                print(json.dumps({"verdict": "unknown", "warning": str(exc)}))
                return 0
            print(f"sim_launcher: {exc}", file=sys.stderr)
            return 1
        inner = (
            ["-m", MODULES[args[0]], *args[1:]]
            if args[0] in MODULES
            else [
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
