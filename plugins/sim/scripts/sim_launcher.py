#!/usr/bin/env python3
"""Run the sim CLI or MCP server inside the pinned sim-tools Docker image.

Launcher-side verification uses SIM_VERIFY_ATTESTATION=auto|require|off.
It verifies lock provenance before pulls and on every prewarm; normal use
does not re-verify an image that is already present locally.
"""

from __future__ import annotations

import contextlib
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
_DOCKER_INFO_TIMEOUT_S = 10
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


def _inside_conversation_container() -> bool:
    """True when running inside an OpenHands docker conversation runtime.

    The runtime injects ``OH_PERSISTENCE_DIR``/``OH_RUNTIME_LAUNCHED_PROFILE``
    into each ``agent-server-conversation-*`` container, which carries no
    docker client — sim tools then have nowhere to launch the pinned
    tools image. ``OH_CONVERSATION_RUNTIME`` is not usable as the signal:
    the runtime sets it to ``local`` inside the container itself.
    """
    if os.environ.get("OH_PERSISTENCE_DIR") or os.environ.get("OH_RUNTIME_LAUNCHED_PROFILE"):
        return True
    with contextlib.suppress(OSError):
        return Path.home() == Path("/var/openhands/.openhands")
    return False


_CONVERSATION_CONTAINER_HINT = (
    " — this appears to be an OpenHands docker conversation "
    "container, which cannot launch tool containers; set the "
    "conversation runtime to local (Agent Canvas -> Settings -> "
    "Application) and start a new conversation"
)


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
        detail = "docker not found on PATH"
        if _inside_conversation_container():
            detail += _CONVERSATION_CONTAINER_HINT
        raise RuntimeError(detail)
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


def _docker_info_security_options(docker: str) -> str | None:
    """Return `docker info` security options, or None when unavailable."""
    try:
        result = subprocess.run(
            [docker, "info", "-f", "{{json .SecurityOptions}}"],
            capture_output=True,
            text=True,
            timeout=_DOCKER_INFO_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _container_user(docker: str) -> str:
    """uid:gid to run the tools container as.

    On rootless Docker the host uid maps to an unmapped subuid inside the
    container user namespace, so bind-mounted workspace writes fail. There
    container root (0:0) maps back to the daemon's owner — the invoking
    user — so 0:0 keeps writes working without weakening isolation (the
    container stays read-only/cap-dropped). On rootful Docker keep the host
    uid so artifacts stay user-owned.
    """
    if "name=rootless" in (_docker_info_security_options(docker) or ""):
        return "0:0"
    return f"{os.getuid()}:{os.getgid()}"


def _docker_argv(docker: str, image: str, source: Path | None, argv: list[str]) -> list[str]:
    workspace = Path(os.environ.get("OPENHANDS_PROJECT_DIR") or Path.cwd()).resolve()
    command = [
        docker,
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        _container_user(docker),
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
    if mode != "docker":
        print(
            "SIM_LAUNCH_MODE host/auto were removed; plugin tools run only in "
            "the pinned sim-tools image",
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
    if docker is None or pin is None or image is None:
        missing: list[str] = []
        if docker is None:
            detail = "docker is not on PATH; install Docker"
            if _inside_conversation_container():
                detail += _CONVERSATION_CONTAINER_HINT
            missing.append(detail)
        if image is None:
            missing.append(
                "no image resolved from the sim image lock; run sim_launcher.py prewarm "
                "or set SIM_TOOLS_IMAGE"
            )
        message = "; ".join(missing)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
