from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import types

from sim import cli, mcp_server
from sim.mcp_server import dispatch_tool, tool_specs


def _call_tool(name: str, arguments: dict[str, object]) -> types.CallToolResult:
    call = cast(
        Coroutine[Any, Any, types.CallToolResult],
        mcp_server.call_tool(name, arguments),
    )
    return asyncio.run(call)


def _mcp_payload(result: types.CallToolResult) -> dict[str, Any]:
    content = result.content[0]
    assert isinstance(content, types.TextContent)
    return cast(dict[str, Any], json.loads(content.text))


def test_cli_run_emits_json_report_and_unknown_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    brief = tmp_path / "board.sim.json"
    brief.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "board",
                "thermal": {"ambient_c": 25, "components": []},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "workspace_root", lambda: tmp_path)

    assert cli.main(["run", brief.name, "--only", "thermal"]) == 3
    report = json.loads(capsys.readouterr().out)
    assert report["verdict"] == "unknown"
    assert (tmp_path / "out" / "board" / "sim-report.json").is_file()


def test_cli_rejects_workspace_escape_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "workspace_root", lambda: tmp_path)

    assert cli.main(["validate", "../outside.sim.json"]) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "fail"


def test_cli_respond_missing_brief_writes_needs_info(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    request = tmp_path / "review.sim-request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "from_system": "circuit",
                "request_id": "SIM-MISSING-001",
                "kind": "thermal",
                "brief_path": "missing.sim.json",
                "question": "Check component temperature.",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "workspace_root", lambda: tmp_path)

    assert cli.main(["respond", request.name]) == 0
    result = json.loads(capsys.readouterr().out)
    response_path = tmp_path / "review.sim-response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))

    assert result["status"] == "needs_info"
    assert response["status"] == "needs_info"
    assert response["request_id"] == "SIM-MISSING-001"


@pytest.mark.parametrize("entry", ["cli", "mcp"])
def test_respond_outside_brief_path_writes_needs_info(
    entry: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = tmp_path / f"{entry}.sim-request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "from_system": "circuit",
                "request_id": f"SIM-OUTSIDE-{entry}",
                "kind": "thermal",
                "brief_path": "../outside.sim.json",
                "question": "Check component temperature.",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "workspace_root", lambda: tmp_path)

    if entry == "cli":
        assert cli.main(["respond", request.name]) == 0
    else:
        result = dispatch_tool("sim_respond", {"request": request.name})
        assert result["status"] == "needs_info"

    response = json.loads((tmp_path / f"{entry}.sim-response.json").read_text(encoding="utf-8"))
    assert response["status"] == "needs_info"
    assert "outside the workspace" in response["reasons"][0]
    if entry == "cli":
        assert json.loads(capsys.readouterr().out)["status"] == "needs_info"


def test_mcp_writing_tools_are_not_annotated_read_only() -> None:
    specs = {item.name: item for item in tool_specs()}
    pdn_annotations = specs["sim_pdn"].annotations
    doctor_annotations = specs["sim_doctor"].annotations

    assert pdn_annotations is not None
    assert doctor_annotations is not None
    assert pdn_annotations.readOnlyHint is False
    assert doctor_annotations.readOnlyHint is True


def test_mcp_unknown_tool_is_transport_error() -> None:
    result = _call_tool("sim_unknown", {})

    assert result.isError is True
    content = result.content[0]
    assert isinstance(content, types.TextContent)
    assert content.text == json.dumps(
        {"verdict": "fail", "detail": "unknown tool 'sim_unknown'"},
        indent=2,
        sort_keys=True,
    )


def test_mcp_dispatch_exception_is_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_dispatch(_name: str, _arguments: dict[str, object]) -> dict[str, object]:
        raise ValueError("dispatch failed")

    monkeypatch.setattr(mcp_server, "dispatch_tool", fail_dispatch)
    result = _call_tool("sim_schema", {})

    assert result.isError is True
    assert _mcp_payload(result) == {"verdict": "fail", "detail": "dispatch failed"}


@pytest.mark.parametrize("verdict", ["fail", "unknown"])
def test_mcp_gate_verdicts_are_not_transport_errors(
    monkeypatch: pytest.MonkeyPatch, verdict: str
) -> None:
    def gate_result(_name: str, _arguments: dict[str, object]) -> dict[str, object]:
        return {"verdict": verdict, "checks": []}

    monkeypatch.setattr(mcp_server, "dispatch_tool", gate_result)
    result = _call_tool("sim_gates", {})

    assert result.isError is False
    assert _mcp_payload(result)["verdict"] == verdict
