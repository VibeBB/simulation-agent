"""VibeBB Record Protocol: typed writers, stdlib hook mirror and Stop enforcement."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import ValidationError

from sim import records

SCRIPTS = Path(__file__).parents[1] / "plugins" / "sim" / "hooks" / "scripts"
HOOK = SCRIPTS / "require_records.py"

IMPRESSION = (
    "The buck regulator report reads as a coherent evidence bundle: the AC "
    "sweep shows the RC rolloff exactly where the analytic WCA placed it, and "
    "every gate carries a measured value beside its bound. What worries me is "
    "the S11 margin at the top of the control band, where the curve flattens "
    "close to the -15 dB line and a layout shift could push it over. A "
    "reviewer could act on the margins table alone, although the deflection "
    "note deserves a second look. Next I would sweep the output capacitor "
    "tolerance wider and re-run the corner analysis. Overall the bundle "
    "communicates intent well, and the remaining risk sits in one RF margin."
)
IMPRESSION_JA = (
    "ACスイープの結果は解析的なWCAの予測と一致しており、レポートだけで判断を進められる構成だと感じた。"
    "一方で制御帯域の上端でS11のマージンが薄く、レイアウトのずれで規格を割る懸念が残る。"
    "レビュアーは各ゲートの測定値と限界を迷わず読めるが、たわみ量の注記は見落とされやすい。"
    "次の工程では出力コンデンサの公差を広げてコーナー解析を回し直したい。"
    "全体としては設計意図が伝わるレポートであり、残リスクはRFマージンに集中している。"
    "発熱の評価は接合部温度で示されているが、周囲温度の根拠が薄いので追記したい。"
    "試験点のピッチは最小間隔を満たしており、治具側の制約もそのままクリアできると判断した。"
    "ただしngspiceの波形は粗い区間があり、測定ステップを詰めて再確認する必要がある。"
    "プロットが失われた場合でも、チェック表の測定値と限界値の併記によって判定の根拠は保全されると考える。"
    "最後に、レビュー工程で各プロットの見所を参照できるよう、チェックリストの対応表を添えることを提案したい。"
)


def _hook_module() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("_records", SCRIPTS / "_records.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOOK_RECORDS = _hook_module()


def _decision(evidence_path: str) -> dict[str, Any]:
    return {
        "id": "buck-lc-cutoff",
        "stage": "analysis",
        "question": "Where should the buck output filter cutoff sit?",
        "principles": [
            "A single-pole RC rolls off at 1/(2*pi*R*C) with -20 dB per decade",
            "IEC 62301-style measurement hygiene: bounds must precede results",
        ],
        "options": [
            {"name": "fc-159hz", "pros": ["meets ripple target"], "cons": ["slow response"]},
            {"name": "fc-1khz", "pros": ["faster"], "cons": ["ripple above limit"]},
        ],
        "chosen": "fc-159hz",
        "rationale": (
            "The ripple budget allows at most 0.76 gain at the switching harmonic, and the "
            "analytic WCA plus the ngspice AC sweep both place 159 Hz inside tolerance "
            "across the declared 5 percent component corners, so the lower cutoff is the "
            "cheapest compliant choice."
        ),
        "evidence": [{"path": evidence_path}, {"reference": "buck converter ripple budget"}],
        "assumptions": ["switching harmonic dominates ripple"],
        "unknowns": ["ESR spread of the output capacitor"],
        "risks": ["lower cutoff slows transient recovery"],
        "revisit_when": "a measured ripple exceeds the 0.76 gain bound",
    }


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    (tmp_path / "out" / "buck" / "plots").mkdir(parents=True)
    (tmp_path / "out" / "buck" / "sim-report.json").write_text(
        '{"schema_version": 1, "verdict": "pass"}\n', encoding="utf-8"
    )
    (tmp_path / "out" / "buck" / "plots" / "summary.png").write_bytes(b"\x89PNG fake")
    return tmp_path


def test_impression_rules() -> None:
    assert records.impression_is_prose(IMPRESSION) == IMPRESSION
    assert records.impression_is_prose(IMPRESSION_JA) == IMPRESSION_JA
    with pytest.raises(ValueError, match="characters"):
        records.impression_is_prose("Looks fine. No issues. Done.")
    with pytest.raises(ValueError, match="sentences"):
        records.impression_is_prose("x" * 500 + ". y")
    with pytest.raises(ValueError, match="repeats"):
        records.impression_is_prose("The report is fine and readable overall. " * 12)
    assert records.sentence_count("Supply is 3.3 V and 5.0 V") == 0
    assert HOOK_RECORDS.impression_errors(IMPRESSION) == []
    assert HOOK_RECORDS.impression_errors(IMPRESSION_JA) == []
    assert HOOK_RECORDS.impression_errors("Looks fine. No issues. Done.")


def test_record_impression_binds_artifacts(workspace: Path) -> None:
    result = records.record_impression(
        {"stage": "analysis", "artifacts": ["out/buck"], "impression": IMPRESSION}
    )
    record = result["record"]
    assert record["artifacts"] == [
        {"path": "out/buck", "sha256": records.tree_sha256(workspace / "out" / "buck")}
    ]
    assert record["sequence"] == 1
    assert HOOK_RECORDS.record_errors("stage_impression", record) == []
    assert HOOK_RECORDS.tree_sha256(workspace / "out" / "buck") == records.tree_sha256(
        workspace / "out" / "buck"
    )
    with pytest.raises(ValueError, match="outside the workspace"):
        records.record_impression(
            {"stage": "analysis", "artifacts": ["/etc/passwd"], "impression": IMPRESSION}
        )
    with pytest.raises(ValueError, match="does not exist"):
        records.record_impression(
            {"stage": "analysis", "artifacts": ["out/missing"], "impression": IMPRESSION}
        )


def test_record_decision_requires_principled_choice(workspace: Path) -> None:
    result = records.record_decision(_decision("out/buck/sim-report.json"))
    record = result["record"]
    digest = hashlib.sha256(
        (workspace / "out" / "buck" / "sim-report.json").read_bytes()
    ).hexdigest()
    assert record["evidence"][0] == {"path": "out/buck/sim-report.json", "sha256": digest}
    assert record["evidence"][1]["reference"].startswith("buck")
    assert HOOK_RECORDS.record_errors("decision", record) == []
    for key, value in (
        ("options", _decision("out/buck/sim-report.json")["options"][:1]),
        ("chosen", "teleport"),
        ("rationale", "because"),
        ("principles", []),
        ("principles", ["vibes"]),
        ("risks", []),
        ("evidence", []),
    ):
        bad = _decision("out/buck/sim-report.json") | {key: value}
        with pytest.raises(ValidationError):
            records.record_decision(bad)
    with pytest.raises(ValidationError):
        records.record_decision(_decision("out/buck/sim-report.json") | {"surprise": 1})


def test_record_vision_review(workspace: Path) -> None:
    result = records.record_vision_review(
        {
            "image_path": "out/buck/plots/summary.png",
            "model": "openhands/kimi-k3",
            "checklist": "sim-summary",
            "findings": [{"category": "margin", "severity": "warning", "note": "S11 close"}],
            "impression": IMPRESSION,
        }
    )
    record = result["record"]
    assert record["image_sha256"] == hashlib.sha256(b"\x89PNG fake").hexdigest()
    assert HOOK_RECORDS.record_errors("vision_review", record) == []
    with pytest.raises(ValidationError, match="image_path or source_event_id"):
        records.record_vision_review({"model": "m", "checklist": "x", "impression": IMPRESSION})
    event = records.record_vision_review(
        {"source_event_id": "a" * 64, "model": "m", "checklist": "x", "impression": IMPRESSION}
    )
    assert event["record"].get("image_sha256") is None


@pytest.mark.parametrize(
    ("kind", "field"),
    [
        ("decision", "principles"),
        ("decision", "options"),
        ("decision", "rationale"),
        ("decision", "evidence"),
        ("decision", "risks"),
        ("decision", "revisit_when"),
        ("decision", "unknowns"),
        ("stage_impression", "impression"),
        ("stage_impression", "artifacts"),
        ("vision_review", "impression"),
        ("vision_review", "model"),
        ("vision_review", "recorded_at"),
        ("vision_review", "event_id"),
    ],
)
def test_hook_mirror_rejects_mutations(workspace: Path, kind: str, field: str) -> None:
    writers = {
        "decision": lambda: records.record_decision(_decision("out/buck/sim-report.json")),
        "stage_impression": lambda: records.record_impression(
            {"stage": "analysis", "artifacts": ["out/buck"], "impression": IMPRESSION}
        ),
        "vision_review": lambda: records.record_vision_review(
            {
                "image_path": "out/buck/plots/summary.png",
                "model": "m",
                "checklist": "sim-summary",
                "impression": IMPRESSION,
            }
        ),
    }
    record = dict(writers[kind]()["record"])
    assert HOOK_RECORDS.record_errors(kind, record) == []
    del record[field]
    assert HOOK_RECORDS.record_errors(kind, record)
    record[field] = ""
    assert HOOK_RECORDS.record_errors(kind, record)


def _hook(mode: str, root: Path, session: str = "s1") -> subprocess.CompletedProcess[str]:
    env = dict(os.environ) | {"OPENHANDS_PROJECT_DIR": str(root)}
    return subprocess.run(
        [sys.executable, str(HOOK), mode],
        input=json.dumps({"session_id": session, "working_dir": str(root)}),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _status(root: Path) -> dict[str, Any]:
    path = root / records.RECORDS_DIR / "records-status.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_stop_without_marker_allows(tmp_path: Path) -> None:
    assert _hook("stop", tmp_path).returncode == 0


def test_stop_clean_session_passes(tmp_path: Path) -> None:
    assert _hook("session-start", tmp_path).returncode == 0
    result = _hook("stop", tmp_path)
    assert result.returncode == 0, result.stdout
    assert _status(tmp_path)["verdict"] == "pass"


def test_stop_enforces_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    assert _hook("session-start", tmp_path).returncode == 0
    out = tmp_path / "out" / "buck"
    out.mkdir(parents=True)
    (out / "sim-report.json").write_text('{"verdict": "pass"}\n', encoding="utf-8")
    (out / "sim-report.md").write_text("# report\n", encoding="utf-8")
    log = tmp_path / records.RECORDS_DIR
    event = {"event_id": "b" * 64, "question": "is the plot sane?", "session_id": "s1"}
    (log / "vision-tool-events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

    denied = _hook("stop", tmp_path)
    assert denied.returncode == 2
    payload = json.loads(denied.stdout)
    assert payload["decision"] == "deny"
    assert "out/buck/sim-report.json" in payload["additionalContext"]
    assert "vision tool event" in payload["additionalContext"]
    assert "no decision record" in payload["additionalContext"]
    assert _status(tmp_path)["verdict"] == "fail"

    records.record_decision(_decision("out/buck/sim-report.json"))
    records.record_impression(
        {"stage": "analysis", "artifacts": ["out/buck"], "impression": IMPRESSION}
    )
    records.record_vision_review(
        {"source_event_id": "b" * 64, "model": "m", "checklist": "q", "impression": IMPRESSION}
    )
    passed = _hook("stop", tmp_path)
    assert passed.returncode == 0, passed.stdout
    assert _status(tmp_path)["verdict"] == "pass"

    (out / "sim-report.json").write_text('{"verdict": "fail"}\n', encoding="utf-8")
    stale = _hook("stop", tmp_path)
    assert stale.returncode == 2
    assert "no fresh stage_impression" in json.loads(stale.stdout)["reason"]

    released = _hook("stop", tmp_path)
    assert released.returncode == 0
    assert json.loads(released.stdout)["decision"] == "allow"
    assert "still unmet" in json.loads(released.stdout)["additionalContext"]


def test_stop_flags_tampered_and_malformed_lines(tmp_path: Path) -> None:
    assert _hook("session-start", tmp_path).returncode == 0
    log = tmp_path / records.RECORDS_DIR
    forged = {
        "schema_version": 1,
        "kind": "stage_impression",
        "plugin": "sim",
        "sequence": 1,
        "event_id": "c" * 64,
        "recorded_at": "2999-01-01T00:00:00+00:00",
        "stage": "analysis",
        "artifacts": [{"path": "out/buck", "sha256": "d" * 64}],
        "impression": "ok.",
    }
    (log / "impressions.jsonl").write_text(json.dumps(forged) + "\n{not json\n", encoding="utf-8")
    result = _hook("stop", tmp_path)
    assert result.returncode == 2
    reason = json.loads(result.stdout)["reason"]
    assert "malformed" in reason
    assert "invalid stage_impression" in reason


def test_viewed_image_needs_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    assert _hook("session-start", tmp_path).returncode == 0
    log = tmp_path / records.RECORDS_DIR
    image = tmp_path / "scope.png"
    image.write_bytes(b"png")
    digest = hashlib.sha256(b"png").hexdigest()
    observation = {
        "event_id": "e" * 64,
        "image_path": str(image),
        "image_sha256": digest,
        "session_id": "s1",
    }
    (log / "image-observations.jsonl").write_text(json.dumps(observation) + "\n", encoding="utf-8")
    assert _hook("stop", tmp_path).returncode == 2
    records.record_vision_review(
        {
            "image_path": "scope.png",
            "model": "m",
            "checklist": "intake-image",
            "impression": IMPRESSION,
        }
    )
    assert _hook("stop", tmp_path).returncode == 0


def test_records_policy_matches_core() -> None:
    policy = HOOK_RECORDS.load_policy(SCRIPTS.parents[1])
    assert policy["plugin"] == records.PLUGIN
    assert policy["records_dir"] == records.RECORDS_DIR.as_posix()
    assert HOOK_RECORDS.IMPRESSION_MIN_CHARS == records.IMPRESSION_MIN_CHARS
    assert HOOK_RECORDS.IMPRESSION_MIN_SENTENCES == records.IMPRESSION_MIN_SENTENCES
    assert HOOK_RECORDS.RATIONALE_MIN_CHARS == records.RATIONALE_MIN_CHARS
    assert HOOK_RECORDS.LOG_FILES == records.LOG_FILES
    assert set(records.Severity.__args__) == HOOK_RECORDS.SEVERITIES
    hooks = json.loads((SCRIPTS.parent / "hooks.json").read_text(encoding="utf-8"))
    for event, mode in (("session_start", "session-start"), ("stop", "stop")):
        commands = [h["command"] for g in hooks[event] for h in g["hooks"]]
        assert any(f'require_records.py" {mode}' in c for c in commands)
