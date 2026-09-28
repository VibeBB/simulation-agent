from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from sim.brief import load_brief
from sim.imports import import_source, write_import_record
from sim.run import run_simulation
from sim.workspace import workspace_path


def test_connectivity_import_is_strict_and_records_sha256(tmp_path: Path) -> None:
    source = tmp_path / "board.connectivity.json"
    payload: dict[str, object] = {
        "schema_version": 1,
        "system": "circuit",
        "connectors": [{"ref": "J1", "cavities": ["1"]}],
        "nets": [
            {
                "ref": "VIN",
                "signal_class": "power",
                "voltage_v": 12.0,
                "current_a": 1.0,
            }
        ],
    }
    source.write_text(json.dumps(payload), encoding="utf-8")

    record = import_source(source.name, tmp_path)
    assert record["system"] == "circuit"
    assert record["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    saved = write_import_record(source.name, tmp_path, tmp_path / "out")
    assert saved == record
    assert json.loads((tmp_path / "out" / "imports.json").read_text(encoding="utf-8")) == [record]


def test_import_rejects_unknown_contract_keys(tmp_path: Path) -> None:
    source = tmp_path / "board.connectivity.json"
    source.write_text(
        json.dumps({"schema_version": 1, "connectors": [], "nets": [], "extra": True}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        import_source(source.name, tmp_path)


def test_mechanical_envelope_import_extracts_anchors(tmp_path: Path) -> None:
    source = tmp_path / "housing.envelope.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "system": "mech",
                "anchors": [
                    {
                        "name": "bulkhead",
                        "kind": "grommet",
                        "position_mm": [10.0, 20.0, 30.0],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    record = import_source(source.name, tmp_path)

    assert record["system"] == "mech"
    extracted = cast(dict[str, object], record["extracted"])
    anchors = cast(list[dict[str, object]], extracted["anchors"])
    assert anchors[0]["name"] == "bulkhead"


def test_wire_contract_import_extracts_load_and_wire_properties(tmp_path: Path) -> None:
    source = tmp_path / "harness.contract.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contract_id": "WH-1",
                "name": "harness",
                "revision": "A",
                "connectors": [
                    {
                        "id": connector,
                        "family": "test",
                        "rated_current_a": 5.0,
                        "rated_voltage_v": 24.0,
                        "cavities": [{"id": "1", "accepts_mm2": [0.25, 0.75]}],
                    }
                    for connector in ("C1", "C2")
                ],
                "wire_types": [
                    {
                        "id": "WT1",
                        "name": "test wire",
                        "gauge_mm2": 0.5,
                        "outer_diameter_mm": 1.2,
                        "resistance_ohm_per_km": 36.0,
                        "ampacity_a": 4.0,
                        "reference_temp_c": 20.0,
                        "insulation_rating_v": 60.0,
                        "insulation_temp_c": 80.0,
                        "min_bend_factor": 6.0,
                    }
                ],
                "nets": [
                    {
                        "id": "N1",
                        "ref": "VDD",
                        "signal_class": "power",
                        "voltage_v": 12.0,
                        "current_a": 1.0,
                    }
                ],
                "wires": [
                    {
                        "id": "W1",
                        "wire_type": "WT1",
                        "net": "N1",
                        "from_endpoint": {"connector": "C1", "cavity": "1"},
                        "to_endpoint": {"connector": "C2", "cavity": "1"},
                        "length_m": 0.5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    record = import_source(source.name, tmp_path)

    assert record["system"] == "wire"
    extracted = cast(dict[str, object], record["extracted"])
    nets = cast(list[dict[str, object]], extracted["nets"])
    wires = cast(list[dict[str, object]], extracted["wires"])
    assert nets[0]["ref"] == "VDD"
    assert wires[0]["id"] == "W1"


def test_import_rejects_paths_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.connectivity.json"
    outside.write_text(
        json.dumps({"schema_version": 1, "connectors": [], "nets": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="outside the workspace"):
        import_source(outside, tmp_path / "workspace")


def test_workspace_paths_reject_symlink_components(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="workspace path contains a symlink"):
        workspace_path(link, tmp_path)


def test_run_replaces_stale_import_records_with_declared_sources(tmp_path: Path) -> None:
    source = tmp_path / "board.connectivity.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "system": "circuit",
                "connectors": [],
                "nets": [
                    {
                        "ref": "VDD",
                        "signal_class": "power",
                        "voltage_v": 3.3,
                        "current_a": 0.5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    brief_path = tmp_path / "board.sim.json"
    payload: dict[str, object] = {
        "schema_version": 1,
        "name": "board",
        "imports": [{"path": source.name, "system": "circuit"}],
        "dft": {
            "nets": [],
            "required": "all",
            "test_points": [],
            "require_debug_header": False,
        },
    }
    brief_path.write_text(json.dumps(payload), encoding="utf-8")
    out_dir = tmp_path / "out" / "board"
    out_dir.mkdir(parents=True)
    (out_dir / "imports.json").write_text('[{"system":"wire"}]\n', encoding="utf-8")

    run_simulation(load_brief(brief_path), brief_path, tmp_path, out_dir, {"dft"})
    payload["imports"] = []
    brief_path.write_text(json.dumps(payload), encoding="utf-8")
    run_simulation(load_brief(brief_path), brief_path, tmp_path, out_dir, {"dft"})

    assert json.loads((out_dir / "imports.json").read_text(encoding="utf-8")) == []


def test_run_rejects_symlinked_generated_output(tmp_path: Path) -> None:
    brief_path = tmp_path / "board.sim.json"
    brief_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "board",
                "dft": {
                    "nets": [],
                    "required": "all",
                    "test_points": [],
                    "require_debug_header": False,
                },
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out" / "board"
    out_dir.mkdir(parents=True)
    protected = tmp_path.parent / f"{tmp_path.name}-protected.json"
    protected.write_text("leave intact\n", encoding="utf-8")
    (out_dir / "imports.json").symlink_to(protected)

    with pytest.raises(ValueError, match="generated output path is a symlink"):
        run_simulation(load_brief(brief_path), brief_path, tmp_path, out_dir, {"dft"})

    assert protected.read_text(encoding="utf-8") == "leave intact\n"
