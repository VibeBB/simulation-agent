"""Workflow asset-path drift tests.

Every ``plugins/sim/...`` path literal referenced from a workflow must exist
(glob-aware for ``*``), and the only ``--user`` value allowed in
``docker run`` invocations is the image's non-root ``sim`` user.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))

PLUGIN_PATH = re.compile(r"plugins/sim/[\w\-/*{}.,]+")
USER_FLAG = re.compile(r"--user\s+(\S+)")

# Paths the publish workflow writes — never committed (ADR: digest lock).
GENERATED = {"plugins/sim/tools-image.json", "docker/image-digests.json"}


def test_workflows_exist() -> None:
    assert WORKFLOWS, "no workflow files found"


def test_plugin_paths_referenced_exist() -> None:
    missing: list[str] = []
    for workflow in WORKFLOWS:
        text = workflow.read_text(encoding="utf-8")
        for literal in PLUGIN_PATH.findall(text):
            path = literal.rstrip(".,'\"")
            if path in GENERATED:
                continue
            if "*" in path:
                if not list(REPO_ROOT.glob(path)):
                    missing.append(f"{workflow.name}: {path}")
            elif not (REPO_ROOT / path).exists():
                missing.append(f"{workflow.name}: {path}")
    assert not missing, f"workflow references missing paths: {missing}"


def test_publish_excludes_generated_pins() -> None:
    publish = (REPO_ROOT / ".github" / "workflows" / "publish-sim-images.yml").read_text(
        encoding="utf-8"
    )
    assert "!docker/image-digests.json" in publish
    assert "!plugins/sim/tools-image.json" in publish


def test_publish_retriggers_for_workflow_and_lock_writer_changes() -> None:
    publish = (REPO_ROOT / ".github" / "workflows" / "publish-sim-images.yml").read_text(
        encoding="utf-8"
    )
    assert ".github/workflows/publish-sim-images.yml" in publish
    assert "scripts/update_image_digest_lock.py" in publish


def test_locked_image_check_validates_and_verifies_provenance() -> None:
    locked = (REPO_ROOT / ".github" / "workflows" / "locked-image-check.yml").read_text(
        encoding="utf-8"
    )
    assert 'entry = data.get("sim_tools")' in locked
    assert 're.fullmatch(r"sha256:[0-9a-f]{64}", digest)' in locked
    assert "gh attestation verify" in locked
    assert "publish-sim-images.yml" in locked


def test_docker_run_user_is_sim() -> None:
    offenders: list[str] = []
    for workflow in WORKFLOWS:
        for line_no, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), start=1):
            if "docker run" not in line:
                continue
            for user in USER_FLAG.findall(line):
                if user != "sim":
                    offenders.append(f"{workflow.name}:{line_no}: --user {user}")
    assert not offenders, f"unexpected --user values: {offenders}"


# ``run:`` shell blocks; body lines are indented deeper than the ``run:`` key.
_RUN_HEADER = re.compile(r"^\s*(?:-\s+)?run:\s*[|>]")
_HEREDOC_ENV_WRITE = re.compile(
    r"<<\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?[^\n]*?>>\s*\"?\$GITHUB_ENV"
)
_ENV_NAME = re.compile(r"\b([A-Z_][A-Z0-9_]*)\s*=")
_LOCAL_ASSIGN = re.compile(
    r"^\s*(?:export\s+|local\s+|readonly\s+|declare\s+-\S+\s+)?([A-Za-z_][A-Za-z0-9_]*)="
)


def _run_blocks(text: str) -> list[list[str]]:
    """Split a workflow into the content lines of each ``run:`` block."""
    blocks: list[list[str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not _RUN_HEADER.match(lines[i]):
            i += 1
            continue
        indent = len(lines[i]) - len(lines[i].lstrip())
        body: list[str] = []
        i += 1
        while i < len(lines):
            line = lines[i]
            if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                break
            body.append(line)
            i += 1
        blocks.append(body)
    return blocks


def _env_writes(body: list[str]) -> set[str]:
    """Names a ``run:`` block appends to ``$GITHUB_ENV``.

    Covers ``echo "NAME=..." >> "$GITHUB_ENV"`` style lines and heredoc
    bodies whose opener redirects to ``$GITHUB_ENV`` (e.g. a ``python3
    <<'PY' >> "$GITHUB_ENV"`` block printing ``NAME=...`` lines).
    """
    names: set[str] = set()
    i = 0
    while i < len(body):
        line = body[i]
        heredoc = _HEREDOC_ENV_WRITE.search(line)
        if heredoc:
            marker = heredoc.group(1)
            i += 1
            while i < len(body) and body[i].strip() != marker:
                names.update(_ENV_NAME.findall(body[i]))
                i += 1
            continue
        if "GITHUB_ENV" in line:
            names.update(_ENV_NAME.findall(line))
        i += 1
    names.discard("GITHUB_ENV")
    return names


def _local_assignments(body: list[str]) -> set[str]:
    """Names assigned as ordinary shell variables in the same block."""
    names: set[str] = set()
    for line in body:
        if "GITHUB_ENV" in line:
            continue
        match = _LOCAL_ASSIGN.match(line)
        if match:
            names.add(match.group(1))
    return names


def test_github_env_writes_not_referenced_in_same_step() -> None:
    """Names appended to ``$GITHUB_ENV`` only take effect in later steps.

    Referencing one in the same ``run:`` block reads an unbound variable —
    the container-audit ``PINNED_IMAGES`` crash shipped exactly this way.
    """
    offenders: list[str] = []
    for workflow in WORKFLOWS:
        for body in _run_blocks(workflow.read_text(encoding="utf-8")):
            if not any("GITHUB_ENV" in line for line in body):
                continue
            written = _env_writes(body) - _local_assignments(body)
            for name in sorted(written):
                shell_ref = re.search(rf"\$\{{?{name}\b", "\n".join(body))
                env_read = re.search(
                    rf"os\.environ(?:\.get)?\s*[\[\(]\s*[\"']?{name}\b",
                    "\n".join(body),
                )
                if shell_ref or env_read:
                    first_line = next(
                        line.strip()
                        for line in body
                        if re.search(rf"\$\{{?{name}\b", line)
                        or re.search(
                            rf"os\.environ(?:\.get)?\s*[\[\(]\s*[\"']?{name}\b",
                            line,
                        )
                    )
                    offenders.append(f"{workflow.name}: {name} used in '{first_line}'")
    assert not offenders, (
        f"$GITHUB_ENV writes apply only to subsequent steps; same-step references: {offenders}"
    )
