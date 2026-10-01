from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import scripts.check_dependency_updates as check_dependency_updates_module
from scripts.check_dependency_updates import (
    HTTP_TIMEOUT_SECONDS,
    ROOT,
    SUBPROCESS_TIMEOUT_SECONDS,
    DependencyStatus,
    _github_latest_tag,  # pyright: ignore[reportPrivateUsage]
    check_docker_args,
    check_docker_base_digest,
    check_docker_commits,
    docker_base_image,
    main,
)


def test_github_latest_tag_treats_timeout_as_fetch_failure():
    def timed_out(url: str) -> list[str]:
        raise subprocess.TimeoutExpired(["git", "ls-remote", "--tags", url], 1)

    assert _github_latest_tag("actions/checkout", timed_out) == ""


def test_github_latest_tag_matches_prefixed_multi_segment_tags():
    def tags(url: str) -> list[str]:
        return ["jdk-27.0-m1", "jdk-27.0.0.0", "jdk-27.0.0.0-m1a", "jdk-27.0.1.0-m1"]

    latest = _github_latest_tag("ibmruntimes/semeru27-binaries", tags, prefix="jdk-")
    assert latest == "jdk-27.0.0.0"


def test_docker_args_report_fetch_failed_on_timeout():
    def timed_out(url: str) -> list[str]:
        raise subprocess.TimeoutExpired(["git", "ls-remote", "--tags", url], 1)

    statuses = check_docker_args(ROOT, list_remote_tags=timed_out)
    uv_status = next(status for status in statuses if status.name == "UV_VERSION")
    assert uv_status.latest == "?"
    assert uv_status.note == "fetch failed"
    assert uv_status.outdated is False
    assert uv_status.fetch_failed is True


def test_docker_dependency_surfaces_match_simulation_image():
    assert docker_base_image(ROOT) == ("ubuntu", "26.04")
    digest_status = check_docker_base_digest(ROOT)[0]
    assert digest_status.current.startswith("sha256:")
    assert digest_status.note.startswith("compare the immutable digest")
    statuses = check_docker_args(ROOT, list_remote_tags=lambda _url: ["0.12.21"])
    assert [(status.name, status.current) for status in statuses] == [("UV_VERSION", "0.12.21")]


def test_docker_commit_pins_compare_with_upstream_heads():
    def latest_commit(url: str) -> str:
        assert url.endswith(".git")
        return "a" * 40

    statuses = check_docker_commits(ROOT, list_remote_head=latest_commit)
    assert {status.name for status in statuses} == {"OPENEMS_COMMIT", "KICAD_RFSIM_COMMIT"}
    assert all(status.latest == "a" * 40 and status.outdated for status in statuses)


def test_subprocess_timeout_is_bounded():
    assert SUBPROCESS_TIMEOUT_SECONDS >= HTTP_TIMEOUT_SECONDS > 0


def test_main_reports_timeout_as_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    def timed_out(repo_root: Path) -> list[DependencyStatus]:
        raise subprocess.TimeoutExpired(["uv", "lock"], SUBPROCESS_TIMEOUT_SECONDS)

    monkeypatch.setattr(check_dependency_updates_module, "check_dependency_updates", timed_out)
    assert main([]) == 1
    assert "dependency update check failed" in capsys.readouterr().err


def test_main_json_includes_unknown_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = [
        DependencyStatus(
            "github-actions",
            "actions/checkout",
            "v7",
            "?",
            ".github/workflows",
            False,
            "fetch failed",
            fetch_failed=True,
        )
    ]

    def fixed_statuses(_root: Path) -> list[DependencyStatus]:
        return statuses

    monkeypatch.setattr(check_dependency_updates_module, "check_dependency_updates", fixed_statuses)
    output = tmp_path / "report.json"
    assert main(["--json", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["unknown_count"] == 1
