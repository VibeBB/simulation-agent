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
