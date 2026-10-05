"""Tests for the SLP v2 liaison protocol (Phase C)."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from sim import cli
from sim.liaison import inbox, load_request, response_path, ux_respond
from sim.mcp_server import dispatch_tool
from sim.records import record_decision, record_impression

SCRIPTS = Path(__file__).parents[1] / "plugins" / "sim" / "hooks" / "scripts"
NOTICE = SCRIPTS / "ux_inbox_notice.py"


def _request(
    tmp_path: Path,
    request_id: str = "ux-sim-001",
    *,
    target: str = "sim",
    risk: str = "low",
    rationale: str = "the purpose needs a documented rationale",
    inputs: list[dict[str, str]] | None = None,
    depends_on: list[str] | None = None,
) -> Path:
    payload = {
        "schema_version": 2,
        "system": "ux-creator",
        "id": request_id,
        "target_agent": target,
        "stage": "design",
        "risk": risk,
        "purpose": "check the enclosure thermals",
        "rationale": rationale,
        "requested_changes": ["rerun the thermal analysis"],
        "inputs": inputs or [],
        "expected_deliverables": ["sim-report.json"],
        "acceptance": ["thermal margin above 10C"],
        "depends_on": depends_on or [],
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    directory = tmp_path / "liaison"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{request_id}.ux-request.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _records(tmp_path: Path) -> tuple[str, str]:
    artifact = tmp_path / "note.txt"
    artifact.write_text("evidence\n", encoding="utf-8")
    decision = record_decision(
        {
            "id": "liaison-solver-choice",
            "stage": "liaison",
            "question": "which solver",
            "principles": ["energy conservation"],
            "options": [
                {"name": "analytic", "pros": ["fast"], "cons": ["coarse"]},
                {"name": "solver", "pros": ["accurate"], "cons": ["slow"]},
            ],
            "chosen": "solver",
            "rationale": "x" * 220,
            "evidence": [{"path": "note.txt"}],
            "assumptions": ["steady state"],
            "unknowns": ["ambient"],
            "risks": ["mesh"],
            "revisit_when": "new data",
        },
        tmp_path,
    )
    impression = record_impression(
        {
            "stage": "liaison",
            "artifacts": ["note.txt"],
            "impression": (
                "The liaison request was handled deterministically, and the "
                "inbox projection correctly separated new, blocked, answered, "
                "and stale work. What worries me is that a stale input can "
                "invalidate a finished answer without the responder noticing. "
                "So the next step is to re-verify every declared input hash "
                "before writing a ux-response, which is exactly what this run "
                "did, leaving the trail auditable for the next session."
            ),
        },
        tmp_path,
    )
    return (
        cast(dict[str, object], decision["record"])["event_id"],  # type: ignore[index]
        cast(dict[str, object], impression["record"])["event_id"],  # type: ignore[index]
    )


def _done_payload(tmp_path: Path, request_id: str) -> dict[str, object]:
    decision_ref, impression_ref = _records(tmp_path)
    report = tmp_path / "out" / "demo" / "sim-report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "checks": [{"id": "thermal.tj", "verdict": "pass", "detail": "ok"}],
            }
        ),
        encoding="utf-8",
    )
    return {
        "request": request_id,
        "status": "done",
        "reason": "all gates passed for the requested change",
        "reports": ["out/demo/sim-report.json"],
        "decision_refs": [decision_ref],
        "impression_refs": [impression_ref],
    }


def test_load_request_happy_path(tmp_path: Path) -> None:
    path = _request(tmp_path)
    request = load_request(path)
    assert request.id == "ux-sim-001"
    assert request.stage == "design"


def test_load_request_rejects_id_mismatch(tmp_path: Path) -> None:
    path = _request(tmp_path, "real-id")
    path.rename(path.parent / "different.ux-request.json")
    with pytest.raises(ValueError, match="file stem"):
        load_request(path.parent / "different.ux-request.json")


def test_high_risk_requires_job_id(tmp_path: Path) -> None:
    path = _request(
        tmp_path,
        risk="high",
        rationale="no job id anywhere in this rationale text",
    )
    with pytest.raises(ValueError, match="UX job id"):
        load_request(path)
    ok = _request(
        tmp_path,
        "ux-sim-002",
        risk="high",
        rationale="tracks UX-JOB-thermal-1 for the enclosure",
    )
    assert load_request(ok).risk == "high"


def test_inbox_states_and_precedence(tmp_path: Path) -> None:
    dep = _request(tmp_path, "aaa-dep")
    dep.unlink()
    stale_input = tmp_path / "input.txt"
    stale_input.write_text("v1\n", encoding="utf-8")
    _request(
        tmp_path,
        "ux-sim-stale",
        inputs=[{"path": "input.txt", "sha256": "0" * 64}],
    )
    _request(tmp_path, "ux-sim-blocked", depends_on=["aaa-dep"])
    _request(tmp_path, "ux-sim-new")
    done_id = "ux-sim-done"
    _request(tmp_path, done_id)
    ux_respond(
        {
            "request": done_id,
            "status": "accepted",
            "reason": "taken on for the next analysis run",
        },
        tmp_path,
    )
    states = {
        cast(dict[str, object], item)["id"]: cast(dict[str, object], item)["state"]
        for item in cast(list[object], inbox(tmp_path)["requests"])
    }
    assert states["ux-sim-stale"] == "stale"
    assert states["ux-sim-blocked"] == "blocked"
    assert states["ux-sim-new"] == "new"
    assert states["ux-sim-done"] == "answered"


def test_inbox_malformed_and_non_sim(tmp_path: Path) -> None:
    _request(tmp_path, "ux-sim-x", target="bard")
    bad = tmp_path / "liaison" / "broken.ux-request.json"
    bad.write_text("{not json", encoding="utf-8")
    result = inbox(tmp_path)
    assert result["requests"] == []
    malformed = cast(list[dict[str, str]], result["malformed"])
    assert len(malformed) == 1
    assert "broken" in malformed[0]["path"]


def test_respond_refuses_non_sim_and_malformed(tmp_path: Path) -> None:
    _request(tmp_path, "other", target="mech")
    with pytest.raises(ValueError, match="not sim"):
        ux_respond({"request": "other", "status": "accepted"}, tmp_path)
    with pytest.raises(FileNotFoundError):
        ux_respond({"request": "missing", "status": "accepted"}, tmp_path)


def test_done_refusals(tmp_path: Path) -> None:
    _request(tmp_path, "ux-sim-001")
    payload = _done_payload(tmp_path, "ux-sim-001")
    cases: list[dict[str, object]] = [
        {**payload, "gate_verdicts": [{"gate": "g", "verdict": "fail"}], "reports": []},
        {**payload, "reports": [], "gate_verdicts": []},
        {
            **payload,
            "reports": [],
            "artifacts": [],
            "gate_verdicts": [{"gate": "g", "verdict": "pass"}],
        },
        {**payload, "decision_refs": []},
        {**payload, "impression_refs": []},
        {**payload, "decision_refs": ["0" * 64]},
    ]
    for kwargs in cases:
        with pytest.raises(ValueError):
            ux_respond(kwargs, tmp_path)
    assert not response_path(tmp_path, "ux-sim-001").exists()


def test_done_refused_when_input_changed(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("old\n", encoding="utf-8")
    _request(
        tmp_path,
        "ux-sim-001",
        inputs=[{"path": "doc.txt", "sha256": "0" * 64}],
    )
    payload = _done_payload(tmp_path, "ux-sim-001")
    with pytest.raises(ValueError, match="changed"):
        ux_respond(payload, tmp_path)


def test_needs_info_requires_questions(tmp_path: Path) -> None:
    _request(tmp_path, "ux-sim-001")
    with pytest.raises(ValueError, match="question"):
        ux_respond(
            {"request": "ux-sim-001", "status": "needs_info", "reason": "x" * 25},
            tmp_path,
        )
    result = ux_respond(
        {
            "request": "ux-sim-001",
            "status": "needs_info",
            "reason": "cannot proceed without the board outline",
            "questions_for_user": ["which enclosure variant?"],
        },
        tmp_path,
    )
    assert result["verdict"] == "pass"
    response = json.loads(response_path(tmp_path, "ux-sim-001").read_text(encoding="utf-8"))
    assert cast(dict[str, object], response)["status"] == "needs_info"
    assert response["responder"] == "sim"
    assert response["schema_version"] == 2


def test_done_writes_response_with_report_expansion(tmp_path: Path) -> None:
    _request(tmp_path, "ux-sim-001")
    payload = _done_payload(tmp_path, "ux-sim-001")
    result = ux_respond(payload, tmp_path)
    response = cast(
        dict[str, object],
        json.loads(Path(cast(str, result["response"])).read_text(encoding="utf-8")),
    )
    gate_verdicts = cast(list[dict[str, str]], response["gate_verdicts"])
    assert gate_verdicts == [{"gate": "thermal.tj", "verdict": "pass"}]
    artifacts = cast(list[dict[str, str]], response["artifacts"])
    assert any(item["path"] == "out/demo/sim-report.json" for item in artifacts)
    assert response["decision_refs"]
    assert response["impression_refs"]
    requests = cast(list[dict[str, object]], inbox(tmp_path)["requests"])
    assert requests[0]["state"] == "answered"


def test_respond_overwrites_atomically(tmp_path: Path) -> None:
    _request(tmp_path, "ux-sim-001")
    for status in ("in_progress", "accepted"):
        ux_respond(
            {"request": "ux-sim-001", "status": status, "reason": ""},
            tmp_path,
        )
    response = json.loads(response_path(tmp_path, "ux-sim-001").read_text(encoding="utf-8"))
    assert cast(dict[str, object], response)["status"] == "accepted"


def test_artifact_symlink_and_escape_rejected(tmp_path: Path) -> None:
    _request(tmp_path, "ux-sim-001")
    outside = tmp_path.parent / "outside-liaison.txt"
    outside.write_text("x", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    for artifact in ("link.txt", "../outside-liaison.txt", "missing.txt"):
        with pytest.raises(ValueError):
            ux_respond(
                {
                    "request": "ux-sim-001",
                    "status": "accepted",
                    "artifacts": [artifact],
                },
                tmp_path,
            )


def test_artifact_directory_tree_hash(tmp_path: Path) -> None:
    _request(tmp_path, "ux-sim-001")
    tree = tmp_path / "out" / "demo"
    tree.mkdir(parents=True)
    (tree / "a.txt").write_text("a", encoding="utf-8")
    (tree / "b.txt").write_text("b", encoding="utf-8")
    result = ux_respond(
        {
            "request": "ux-sim-001",
            "status": "accepted",
            "artifacts": ["out/demo"],
        },
        tmp_path,
    )
    response = cast(
        dict[str, object],
        json.loads(Path(cast(str, result["response"])).read_text(encoding="utf-8")),
    )
    tree_artifacts = cast(list[dict[str, str]], response["artifacts"])
    assert tree_artifacts[0]["path"] == "out/demo"
    assert len(tree_artifacts[0]["sha256"]) == 64


def test_mcp_and_cli_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    _request(tmp_path, "ux-sim-001")
    payload = dispatch_tool("sim_ux_inbox", {})
    assert cast(list[dict[str, object]], payload["requests"])[0]["state"] == "new"
    result = dispatch_tool(
        "sim_ux_respond",
        {"request": "ux-sim-001", "status": "deferred", "reason": "d" * 25},
    )
    assert result["verdict"] == "pass"
    assert cli.main(["ux-inbox"]) == 0 if _monkeypatch_root(monkeypatch, tmp_path) else 0
    out = cast(dict[str, object], json.loads(capsys.readouterr().out))
    assert cast(list[dict[str, object]], out["requests"])[0]["state"] == "answered"
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(
        json.dumps({"request": "ux-sim-001", "status": "accepted"}), encoding="utf-8"
    )
    assert cli.main(["ux-respond", "--json", "payload.json"]) == 0


def _monkeypatch_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> bool:
    monkeypatch.setattr(cli, "workspace_root", lambda: tmp_path)
    return True


def test_notice_hook_lists_pending(tmp_path: Path) -> None:
    _request(tmp_path, "ux-sim-001")
    _request(tmp_path, "other-one", target="bard")
    (tmp_path / "liaison" / "bad.ux-request.json").write_text("{bad", encoding="utf-8")
    env = {"OPENHANDS_PROJECT_DIR": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(NOTICE)],
        env={**dict(__import__("os").environ), **env},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    output = cast(dict[str, object], json.loads(result.stdout))
    context = str(output["additionalContext"])
    assert "ux-sim-001" in context
    assert "sim_ux_inbox" in context
    assert "1 malformed" in context


def test_notice_hook_silent_when_empty(tmp_path: Path) -> None:
    env = {"OPENHANDS_PROJECT_DIR": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(NOTICE)],
        env={**dict(__import__("os").environ), **env},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_request_schema_is_strict(tmp_path: Path) -> None:
    path = _request(tmp_path, "ux-sim-001")
    payload = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    for key in ("inputs", "depends_on", "expected_deliverables", "acceptance"):
        missing = {**payload}
        del missing[key]
        path.write_text(json.dumps(missing), encoding="utf-8")
        with pytest.raises(ValueError):
            load_request(path)
    for key in ("expected_deliverables", "acceptance", "requested_changes"):
        blank = {**payload, key: [""]}
        path.write_text(json.dumps(blank), encoding="utf-8")
        with pytest.raises(ValueError):
            load_request(path)
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_request(path).id == "ux-sim-001"


def test_depends_on_accepts_any_responder(tmp_path: Path) -> None:
    _request(tmp_path, "aaa-dep")
    _request(tmp_path, "ux-sim-001", depends_on=["aaa-dep"])
    before = cast(list[dict[str, object]], inbox(tmp_path)["requests"])
    assert before[0]["state"] == "blocked"
    response_path(tmp_path, "aaa-dep").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "system": "ux-creator",
                "request": "aaa-dep",
                "responder": "mech",
                "status": "accepted",
            }
        ),
        encoding="utf-8",
    )
    after = cast(list[dict[str, object]], inbox(tmp_path)["requests"])
    assert after[0]["state"] == "new"


def test_inbox_skips_invalid_other_target(tmp_path: Path) -> None:
    (tmp_path / "liaison").mkdir()
    other = tmp_path / "liaison" / "not-ours.ux-request.json"
    other.write_text(
        json.dumps({"target_agent": "mech", "garbage": True}),
        encoding="utf-8",
    )
    ours = tmp_path / "liaison" / "ours.ux-request.json"
    ours.write_text(json.dumps({"target_agent": "sim"}), encoding="utf-8")
    result = inbox(tmp_path)
    malformed = cast(list[dict[str, str]], result["malformed"])
    assert len(malformed) == 1
    assert "ours" in malformed[0]["path"]


def test_forged_record_ref_is_refused(tmp_path: Path) -> None:
    _request(tmp_path, "ux-sim-001")
    decision_ref, _ = _records(tmp_path)
    log = tmp_path / "observations" / "sim" / "decisions.jsonl"
    forged = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    forged["rationale"] = "forged rationale keeps a forged event id"
    forged["event_id"] = hashlib.sha256(b"forged").hexdigest()
    log.write_text(
        log.read_text(encoding="utf-8") + json.dumps(forged) + "\n",
        encoding="utf-8",
    )
    payload = _done_payload(tmp_path, "ux-sim-001")
    with pytest.raises(ValueError, match=re.escape("is not a decisions.jsonl event_id")):
        ux_respond({**payload, "decision_refs": [str(forged["event_id"])]}, tmp_path)
    result = ux_respond({**payload, "decision_refs": [decision_ref]}, tmp_path)
    assert result["status"] == "done"


def test_cli_respond_decision_ref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    _request(tmp_path, "ux-sim-001")
    decision_ref, _ = _records(tmp_path)
    (tmp_path / "request.sim-request.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "request_id": "r1",
                "brief_path": "brief.json",
                "kind": "any",
                "from_system": "circuit",
                "question": "does the response carry a decision ref?",
            }
        ),
        encoding="utf-8",
    )
    # brief is missing -> needs_info response; the flag parses and the
    # response file is written
    assert cli.main(["respond", "request.sim-request.json", "--decision-ref", decision_ref]) == 0
    response = json.loads((tmp_path / "request.sim-response.json").read_text(encoding="utf-8"))
    assert cast(dict[str, object], response)["status"] == "needs_info"


def test_write_response_rejects_unknown_decision_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sim.responses import write_response

    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    with pytest.raises(ValueError, match=re.escape("not a decisions.jsonl event_id")):
        write_response(tmp_path / "r.json", "r1", "needs_info", decision_refs=["0" * 64])


def test_family_request_id_with_dot_and_underscore_is_accepted(tmp_path: Path) -> None:
    path = _request(tmp_path, "k.v_1", depends_on=["k.base_0"])
    request = load_request(path)
    assert request.id == "k.v_1"
    assert request.depends_on == ["k.base_0"]
