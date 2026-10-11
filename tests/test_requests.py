from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sim._envelope import check_envelope, sidecar_path
from sim.requests import load_request
from sim.responses import SimulationResponse, write_response


def test_request_response_flow_hashes_report(tmp_path: Path) -> None:
    request_path = tmp_path / "review.sim-request.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "from_system": "circuit",
                "request_id": "SIM-42",
                "kind": "pdn",
                "brief_path": "board.sim.json",
                "question": "Check the regulator rail.",
            }
        ),
        encoding="utf-8",
    )
    request = load_request(request_path)
    report = tmp_path / "sim-report.json"
    report.write_text('{"verdict":"pass"}\n', encoding="utf-8")

    response_path = write_response(
        request_path,
        request.request_id,
        "accepted",
        "pass",
        report,
    )
    response = json.loads(response_path.read_text(encoding="utf-8"))
    assert response["request_id"] == "SIM-42"
    assert response["sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()


def test_request_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "bad.sim-request.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "from_system": "circuit",
                "request_id": "SIM-43",
                "kind": "any",
                "brief_path": "board.sim.json",
                "question": "Check.",
                "verdict": "pass",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="could not load simulation request"):
        load_request(path)


@pytest.mark.parametrize(
    ("status", "verdict"),
    [("accepted", "fail"), ("accepted", None), ("rejected", "pass")],
)
def test_response_requires_matching_deterministic_verdict(
    status: str,
    verdict: str | None,
) -> None:
    with pytest.raises(ValueError):
        SimulationResponse.model_validate(
            {"request_id": "SIM-44", "status": status, "verdict": verdict}
        )


def test_response_rejects_symlinked_output(tmp_path: Path) -> None:
    request_path = tmp_path / "review.sim-request.json"
    request_path.write_text("{}", encoding="utf-8")
    protected = tmp_path / "protected.json"
    protected.write_text("leave intact\n", encoding="utf-8")
    output = tmp_path / "review.sim-response.json"
    output.symlink_to(protected)

    with pytest.raises(ValueError, match="generated output path is a symlink"):
        write_response(request_path, "SIM-45", "needs_info")

    assert protected.read_text(encoding="utf-8") == "leave intact\n"


def test_accepted_response_requires_hashed_report() -> None:
    with pytest.raises(ValueError, match="require a hashed report"):
        SimulationResponse.model_validate(
            {
                "request_id": "SIM-46",
                "request_sha256": "0" * 64,
                "status": "accepted",
                "verdict": "pass",
            }
        )


def test_response_carries_envelope_v3_and_broken_log_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    request_path = tmp_path / "env.sim-request.json"
    request_path.write_text("{}\n", encoding="utf-8")
    report = tmp_path / "sim-report.json"
    report.write_text('{"verdict":"pass"}\n', encoding="utf-8")
    output = write_response(request_path, "SIM-47", "accepted", "pass", report)
    assert check_envelope(output, "sim", tmp_path)[0] == "pass"
    log = tmp_path / "observations" / "sim" / "decisions.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("{forged\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fail integrity"):
        write_response(request_path, "SIM-47", "accepted", "pass", report)
    assert not output.exists() and not sidecar_path(output).exists()
