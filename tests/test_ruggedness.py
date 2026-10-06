from __future__ import annotations

import math
from typing import Any

import pytest
from pydantic import ValidationError

from sim.analysis import drop_peak_g, plate_natural_frequency, run_ruggedness
from sim.brief import RuggednessSection, SimulationBrief
from sim.requests import SimulationRequest

PLATE: dict[str, Any] = {
    "width_mm": 100,
    "depth_mm": 80,
    "thickness_mm": 1.6,
    "youngs_mpa": 18600,
    "poisson": 0.12,
    "density_kg_m3": 1850,
    "component_mass_g": 20,
}


def _part(**overrides: Any) -> dict[str, Any]:
    return {
        "ref": "U1",
        "x_mm": 0,
        "y_mm": 0,
        "length_mm": 20,
        "parallel_to": "width",
        "steinberg_c": 1.0,
        **overrides,
    }


def _section(**overrides: Any) -> RuggednessSection:
    return RuggednessSection.model_validate({"plate": PLATE, **overrides})


def _verdicts(section: RuggednessSection) -> dict[str, str]:
    return {item.id: item.verdict for item in run_ruggedness(section)}


def test_plate_frequency_matches_hand_calculation() -> None:
    rigidity = 18600e6 * 0.0016**3 / (12 * (1 - 0.12**2))
    areal = 1850 * 0.0016 + 0.02 / (0.1 * 0.08)
    expected = math.pi / 2 * math.sqrt(rigidity / areal) * (1 / 0.1**2 + 1 / 0.08**2)
    plate = _section(drop=None, ingress={"code": "IP40", "sealed": False}).plate
    assert plate is not None
    assert plate_natural_frequency(plate) == pytest.approx(expected)
    assert 430 < expected < 445


@pytest.mark.parametrize(("delta", "expected"), [(-1, "pass"), (0, "pass"), (1, "fail")])
def test_min_fn_boundary(delta: float, expected: str) -> None:
    probe = _section(vibration={"psd_g2_hz": 0.01, "parts": [_part()]})
    assert probe.plate is not None
    fn = plate_natural_frequency(probe.plate)
    section = _section(
        vibration={"psd_g2_hz": 0.01, "min_fn_hz": fn + delta * 1e-6, "parts": [_part()]}
    )
    assert _verdicts(section)["ruggedness.vibration.fn"] == expected


def test_steinberg_displacement_pass_fail_and_edge() -> None:
    mild = _section(vibration={"psd_g2_hz": 0.01, "parts": [_part()]})
    assert _verdicts(mild)["ruggedness.vibration.U1"] == "pass"
    harsh = _section(vibration={"psd_g2_hz": 5.0, "parts": [_part(steinberg_c=2.25)]})
    assert _verdicts(harsh)["ruggedness.vibration.U1"] == "fail"
    edge = _section(vibration={"psd_g2_hz": 5.0, "parts": [_part(x_mm=50)]})
    assert _verdicts(edge)["ruggedness.vibration.U1"] == "pass"
    outside = _section(vibration={"psd_g2_hz": 0.01, "parts": [_part(x_mm=50.1)]})
    assert _verdicts(outside)["ruggedness.vibration.U1"] == "unknown"


def test_drop_peak_boundary() -> None:
    drop = {"height_mm": 1000, "pulse_ms": 1, "restitution": 0}
    peak = math.pi * math.sqrt(2 * 9.80665) / (2 * 0.001) / 9.80665
    section = RuggednessSection.model_validate({"drop": {**drop, "max_shock_g": 800}})
    assert section.drop is not None
    assert drop_peak_g(section.drop) == pytest.approx(peak)
    for limit, expected in ((peak - 1e-6, "fail"), (peak + 1e-6, "pass")):
        section = RuggednessSection.model_validate({"drop": {**drop, "max_shock_g": limit}})
        assert _verdicts(section)["ruggedness.drop.peak_g"] == expected


@pytest.mark.parametrize(
    ("code", "openings", "sealed", "expected"),
    [
        ("IP40", [0.99], False, {"ruggedness.ingress.solids": "pass"}),
        ("IP40", [1.0], False, {"ruggedness.ingress.solids": "fail"}),
        ("IP2X", [12.4, 3.0], False, {"ruggedness.ingress.solids": "pass"}),
        (
            "IP54",
            [],
            True,
            {"ruggedness.ingress.solids": "unknown", "ruggedness.ingress.water": "unknown"},
        ),
        ("IPX4", [2.0], False, {"ruggedness.ingress.water": "fail"}),
        ("IPX4", [2.0], True, {"ruggedness.ingress.water": "unknown"}),
        ("IPXX", [20.0], False, {}),
    ],
)
def test_ingress_decision_table(
    code: str, openings: list[float], sealed: bool, expected: dict[str, str]
) -> None:
    section = RuggednessSection.model_validate(
        {"ingress": {"code": code, "openings_min_mm": openings, "sealed": sealed}}
    )
    assert _verdicts(section) == expected


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"vibration": {"psd_g2_hz": 0.01, "parts": [_part()]}},
        {"plate": PLATE, "vibration": {"psd_g2_hz": 0.01, "parts": [_part(), _part()]}},
        {"ingress": {"code": "IP7X", "sealed": False}},
        {"ingress": {"code": "IP40", "openings_min_mm": [0], "sealed": False}},
        {"drop": {"height_mm": 1, "pulse_ms": 1, "restitution": 1.5, "max_shock_g": 1}},
    ],
)
def test_malformed_sections_are_rejected(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RuggednessSection.model_validate(payload)


def test_brief_and_request_accept_ruggedness() -> None:
    brief = SimulationBrief.model_validate(
        {
            "schema_version": 1,
            "name": "demo",
            "ruggedness": {"ingress": {"code": "IP40", "sealed": False}},
        }
    )
    assert brief.ruggedness is not None
    request = SimulationRequest.model_validate(
        {
            "schema_version": 1,
            "from_system": "mech",
            "request_id": "r1",
            "kind": "ruggedness",
            "brief_path": "demo.sim.json",
            "question": "drop, vibration and IP",
        }
    )
    assert request.kind == "ruggedness"
