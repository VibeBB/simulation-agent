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
                "drawing": {"legal_owner": "VibeBB", "language": "en"},
                "simulation": {"rails": [], "response_path": "sim/WH-1.pdn.sim-response.json"},
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


def test_emc_imports_only_voltage_for_declared_interface_nets(tmp_path: Path) -> None:
    source = tmp_path / "board.connectivity.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "system": "circuit",
                "connectors": [
                    {"ref": "J1", "cavities": ["1"]},
                    {"ref": "J2", "cavities": ["1"]},
                ],
                "nets": [
                    {
                        "ref": "VIN",
                        "signal_class": "power",
                        "voltage_v": 12.0,
                        "current_a": 1.0,
                    },
                    {
                        "ref": "GND",
                        "signal_class": "ground",
                        "voltage_v": 0.0,
                        "current_a": 0.0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    brief_path = tmp_path / "board.sim.json"
    brief_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "board",
                "imports": [{"path": source.name, "system": "circuit"}],
                "emc": {
                    "interfaces": [
                        {
                            "connector_ref": "J1",
                            "nets": ["VIN"],
                            "esd_level": 2,
                            "external": True,
                        }
                    ],
                    "protections": [
                        {
                            "ref": "D1",
                            "nets": ["VIN"],
                            "vrwm_v": 12,
                            "vclamp_v": 18,
                            "esd_rating_contact_kv": 8,
                            "distance_to_connector_mm": 2,
                        }
                    ],
                    "protected_devices": [{"ref": "U1", "nets": ["VIN"], "abs_max_v": 20}],
                    "signals": [{"net": "VIN"}],
                },
            }
        ),
        encoding="utf-8",
    )

    report = run_simulation(
        load_brief(brief_path),
        brief_path,
        tmp_path,
        tmp_path / "out" / "board",
        {"emc"},
    )
    checks: dict[str, dict[str, object]] = {
        str(item["id"]): item for item in cast(list[dict[str, object]], report["checks"])
    }

    assert checks["emc.interface.J2"]["verdict"] == "unknown"
    assert checks["emc.interface.J2"]["detail"] == "declare the nets of this external connector"
    assert checks["emc.protection.J1.VIN"]["verdict"] == "pass"
    assert "emc.critical_length.VIN" not in checks
    assert not any(check_id.startswith("emc.signal.") for check_id in checks)


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


def _fw_power(tmp_path: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {
        "schema_version": 1,
        "system": "firmware",
        "artifact_kind": "firmware_power",
        "design": "kettle",
        "contract_sha256": "a" * 64,
        "mcu_ref": "U1",
        "supply_net": "+3V3",
        "peak_current_a": 0.025,
        "average_current_a": 0.025 * 0.1 + 0.0002 * 0.9,
        "modes": [
            {"id": "run", "kind": "run", "current_a": 0.025, "duty": 0.1},
            {"id": "sleep", "kind": "deep_sleep", "current_a": 0.0002, "duty": 0.9},
        ],
    }
    payload.update(overrides)
    path = tmp_path / "kettle.fw-power.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_firmware_power_import_extracts_peak_supply_current(tmp_path: Path) -> None:
    path = _fw_power(tmp_path)
    source = import_source(path.name, tmp_path)
    assert source["system"] == "firmware"
    assert source["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    extracted = cast(dict[str, object], source["extracted"])
    assert extracted["nets"] == [
        {
            "ref": "+3V3",
            "current_a": 0.025,
            "average_current_a": pytest.approx(0.00268),
            "mcu_ref": "U1",
        }
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"peak_current_a": 0.02},
        {"average_current_a": 0.01},
        {"artifact_kind": "firmware_pinmap"},
        {"modes": []},
        {"extra": True},
    ],
)
def test_firmware_power_import_rejects_inconsistent_exports(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        import_source(_fw_power(tmp_path, **overrides).name, tmp_path)


def _fw_pdn_brief(tmp_path: Path, current: str, imports: list[dict[str, str]]) -> Path:
    brief = tmp_path / "kettle.sim.json"
    brief.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "kettle",
                "imports": imports,
                "pdn": {
                    "rails": [
                        {
                            "name": "v3v3",
                            "source_v": 3.3,
                            "max_drop_v": 0.1,
                            "source_node": "VIN",
                            "nodes": ["VIN", "U1"],
                            "branches": [
                                {
                                    "ref": "R1",
                                    "from_node": "VIN",
                                    "to_node": "U1",
                                    "kind": "resistor",
                                    "resistance_ohm": 0.5,
                                }
                            ],
                            "loads": [{"node": "U1", "current_a": current}],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    return brief


def _drop(tmp_path: Path, brief: Path) -> dict[str, object]:
    out_dir = tmp_path / "out" / "kettle"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = run_simulation(load_brief(brief), brief, tmp_path, out_dir, {"pdn"})
    by_id = {item["id"]: item for item in report["checks"]}
    return cast(dict[str, object], by_id["pdn.v3v3.drop.U1"])


def test_pdn_load_draws_the_imported_firmware_peak_current(tmp_path: Path) -> None:
    path = _fw_power(tmp_path)
    brief = _fw_pdn_brief(
        tmp_path, "import:firmware:+3V3", [{"path": path.name, "system": "firmware"}]
    )
    drop = _drop(tmp_path, brief)
    assert drop["verdict"] == "pass"
    assert drop["measured"] == pytest.approx(0.0125)


def test_pdn_firmware_current_needs_the_firmware_import(tmp_path: Path) -> None:
    path = _fw_power(tmp_path)
    connectivity = tmp_path / "board.connectivity.json"
    connectivity.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "system": "circuit",
                "connectors": [],
                "nets": [
                    {"ref": "+3V3", "signal_class": "power", "voltage_v": 3.3, "current_a": 1.0}
                ],
            }
        ),
        encoding="utf-8",
    )
    brief = _fw_pdn_brief(
        tmp_path,
        "import:firmware:+3V3",
        [{"path": connectivity.name, "system": "circuit"}],
    )
    out_dir = tmp_path / "out" / "kettle"
    out_dir.mkdir(parents=True)
    report = run_simulation(load_brief(brief), brief, tmp_path, out_dir, {"pdn"})
    unknown = [item for item in report["checks"] if item["verdict"] == "unknown"]
    assert any("+3V3" in item["detail"] for item in unknown)
    assert report["verdict"] != "pass"
    assert path.exists()


def test_pdn_firmware_import_must_be_declared_as_firmware(tmp_path: Path) -> None:
    path = _fw_power(tmp_path)
    brief = _fw_pdn_brief(
        tmp_path, "import:firmware:+3V3", [{"path": path.name, "system": "circuit"}]
    )
    out_dir = tmp_path / "out" / "kettle"
    out_dir.mkdir(parents=True)
    report = run_simulation(load_brief(brief), brief, tmp_path, out_dir, {"pdn"})
    assert any(
        item["id"].startswith("imports.circuit") and item["verdict"] == "unknown"
        for item in report["checks"]
    )
    assert report["verdict"] != "pass"
