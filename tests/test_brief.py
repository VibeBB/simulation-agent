from __future__ import annotations

import pytest

from sim.brief import SimulationBrief


def test_brief_requires_at_least_one_analysis_section() -> None:
    with pytest.raises(ValueError, match="at least one analysis section"):
        SimulationBrief.model_validate({"schema_version": 1, "name": "empty"})


def test_brief_rejects_unknown_fields_and_non_finite_numbers() -> None:
    with pytest.raises(ValueError):
        SimulationBrief.model_validate(
            {
                "schema_version": 1,
                "name": "bad",
                "thermal": {"ambient_c": 25, "unexpected": True},
            }
        )
    with pytest.raises(ValueError):
        SimulationBrief.model_validate(
            {
                "schema_version": 1,
                "name": "bad",
                "thermal": {"ambient_c": float("nan")},
            }
        )


def test_spice_rejects_multiline_directive_injection() -> None:
    with pytest.raises(ValueError, match="single-line directives"):
        SimulationBrief.model_validate(
            {
                "schema_version": 1,
                "name": "bad",
                "spice": {
                    "deck": {
                        "elements": [
                            {
                                "ref": "R1",
                                "kind": "R",
                                "nodes": ["in", "0"],
                                "value": "1k",
                            }
                        ],
                        "analyses": [".op\n.control\nshell touch marker\n.endc"],
                    }
                },
            }
        )


def test_pdn_rejects_loads_attached_to_source_nodes() -> None:
    with pytest.raises(ValueError, match="fixed source node"):
        SimulationBrief.model_validate(
            {
                "schema_version": 1,
                "name": "bad",
                "pdn": {
                    "rails": [
                        {
                            "name": "VDD",
                            "source_v": 3.3,
                            "max_drop_v": 0.1,
                            "source_node": "VDD",
                            "nodes": ["VDD", "LOAD"],
                            "branches": [
                                {
                                    "ref": "R1",
                                    "from_node": "VDD",
                                    "to_node": "LOAD",
                                    "kind": "resistor",
                                    "resistance_ohm": 0.1,
                                }
                            ],
                            "loads": [{"node": "VDD", "current_a": 1}],
                        }
                    ]
                },
            }
        )


def test_wca_output_names_cannot_escape_report_directories() -> None:
    with pytest.raises(ValueError):
        SimulationBrief.model_validate(
            {
                "schema_version": 1,
                "name": "bad",
                "wca": {
                    "parameters": [{"name": "R1", "nominal": 10, "tol_pct": 1}],
                    "outputs": [{"name": "../escape", "expression": "R1", "min": 1}],
                    "methods": ["EVA"],
                },
            }
        )


def test_brief_rejects_duplicate_emc_refs_and_invalid_pdn_units() -> None:
    with pytest.raises(ValueError, match="interface connector refs must be unique"):
        SimulationBrief.model_validate(
            {
                "schema_version": 1,
                "name": "bad",
                "emc": {
                    "interfaces": [
                        {"connector_ref": "J1", "nets": ["VIN"], "external": True},
                        {"connector_ref": "J1", "nets": ["GND"], "external": True},
                    ]
                },
            }
        )
    with pytest.raises(ValueError):
        SimulationBrief.model_validate(
            {
                "schema_version": 1,
                "name": "bad",
                "pdn": {
                    "rails": [
                        {
                            "name": "VDD",
                            "source_v": 3.3,
                            "max_drop_v": 0.1,
                            "source_node": "SRC",
                            "nodes": ["SRC", "LOAD"],
                            "branches": [
                                {
                                    "ref": "T1",
                                    "from_node": "SRC",
                                    "to_node": "LOAD",
                                    "kind": "trace",
                                    "length_m": 0.1,
                                    "width_mm": 1,
                                    "copper_oz": 1,
                                }
                            ],
                            "loads": [{"node": "LOAD", "current_a": 0.1}],
                        }
                    ]
                },
            }
        )
