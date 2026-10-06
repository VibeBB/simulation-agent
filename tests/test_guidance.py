from __future__ import annotations

import re

import pytest

from sim.analysis import (
    drop_peak_g,
    plate_natural_frequency,
    run_ruggedness,
    run_thermal,
)
from sim.brief import RuggednessSection, RuggedPlate, ThermalSection
from sim.gates import GateCheck, check

PLATE = {
    "width_mm": 100,
    "depth_mm": 80,
    "thickness_mm": 1.6,
    "youngs_mpa": 22000,
    "poisson": 0.12,
    "density_kg_m3": 1850,
    "component_mass_g": 20,
}


def _by_id(checks: list[GateCheck]) -> dict[str, GateCheck]:
    return {item.id: item for item in checks}


def _value(lines: list[str], key: str) -> float:
    for line in lines:
        match = re.match(rf"{re.escape(key)} [≤≥] ([0-9.e+-]+)", line)
        if match:
            return float(match.group(1))
    raise AssertionError(f"{key} not in {lines}")


def _scalar(power: float, theta: float, tj_max: float = 100) -> ThermalSection:
    return ThermalSection.model_validate(
        {
            "ambient_c": 40,
            "components": [
                {"ref": "U1", "power_w": power, "tj_max_c": tj_max, "derating_margin_c": 10},
            ],
            "network": None,
        }
        | {
            "components": [
                {
                    "ref": "U1",
                    "power_w": power,
                    "tj_max_c": tj_max,
                    "derating_margin_c": 10,
                    "path": {"theta_ja_c_per_w": theta},
                }
            ]
        }
    )


def test_passing_check_carries_margin_without_guidance() -> None:
    result = _by_id(run_thermal(_scalar(1, 20)))["thermal.U1.tj"]
    assert result.verdict == "pass"
    assert result.margin == pytest.approx(90 - 60)
    assert result.to_dict()["guidance"] == []


def test_scalar_thermal_guidance_inverts_to_the_limit() -> None:
    result = _by_id(run_thermal(_scalar(2, 40)))["thermal.U1.tj"]
    assert result.verdict == "fail"
    assert result.margin == pytest.approx(90 - 120)
    lines = result.guidance or []
    assert "dTj/dP(U1) = 40 °C/W" in lines[0]
    assert _value(lines, "power_w(U1)") == pytest.approx(50 / 40, rel=1e-5)
    assert _value(lines, "θ(U1)") == pytest.approx(25)
    assert _value(lines, "ambient_c") == pytest.approx(10)
    fixed = _by_id(run_thermal(_scalar(_value(lines, "power_w(U1)"), 40)))["thermal.U1.tj"]
    assert fixed.verdict == "pass"
    assert fixed.margin == pytest.approx(0, abs=1e-4)


def test_ambient_above_limit_says_own_power_cannot_fix_it() -> None:
    section = ThermalSection.model_validate(
        {
            "ambient_c": 95,
            "components": [
                {
                    "ref": "U1",
                    "power_w": 1,
                    "tj_max_c": 100,
                    "derating_margin_c": 10,
                    "path": {"theta_ja_c_per_w": 5},
                },
            ],
        }
    )
    lines = _by_id(run_thermal(section))["thermal.U1.tj"].guidance or []
    assert any("even at zero own power" in line for line in lines)
    assert not any(line.startswith("power_w") for line in lines)


def test_network_guidance_separates_own_and_coupled_heating() -> None:
    section = ThermalSection.model_validate(
        {
            "ambient_c": 25,
            "components": [
                {"ref": "U1", "power_w": 3, "tj_max_c": 80},
                {"ref": "U2", "power_w": 2, "tj_max_c": 150},
            ],
            "network": {
                "nodes": ["ambient", "board", "U1", "U2"],
                "resistances": [
                    {"a": "U1", "b": "board", "c_per_w": 10},
                    {"a": "U2", "b": "board", "c_per_w": 5},
                    {"a": "board", "b": "ambient", "c_per_w": 8},
                ],
                "power_nodes": {"U1": 3, "U2": 2},
                "ambient_node": "ambient",
            },
        }
    )
    u1 = _by_id(run_thermal(section))["thermal.U1.tj"]
    assert u1.verdict == "fail"
    assert u1.measured == pytest.approx(25 + 5 * 8 + 3 * 10)
    lines = u1.guidance or []
    assert "dTj/dP(U1) = 18 °C/W" in lines[0]
    budget = _value(lines, "power_w(U1)")
    assert budget == pytest.approx((80 - 25 - 2 * 8) / 18, rel=1e-5)
    patched = section.model_copy(
        update={
            "network": section.network.model_copy(  # type: ignore[union-attr]
                update={"power_nodes": {"U1": budget, "U2": 2}}
            )
        }
    )
    assert _by_id(run_thermal(patched))["thermal.U1.tj"].margin == pytest.approx(0, abs=1e-4)


def test_drop_guidance_inverts_to_the_limit() -> None:
    section = RuggednessSection.model_validate(
        {"drop": {"height_mm": 1000, "pulse_ms": 2, "restitution": 0.5, "max_shock_g": 450}}
    )
    result = _by_id(run_ruggedness(section))["ruggedness.drop.peak_g"]
    assert result.verdict == "fail"
    lines = result.guidance or []
    assert section.drop is not None
    for key in ("pulse_ms", "height_mm", "restitution"):
        fixed = section.drop.model_copy(update={key: _value(lines, key)})
        assert drop_peak_g(fixed) == pytest.approx(450, rel=1e-5)


def test_plate_fn_guidance_inverts_to_the_target() -> None:
    plate = RuggedPlate.model_validate(PLATE)
    target = plate_natural_frequency(plate) * 1.05
    section = RuggednessSection.model_validate(
        {
            "plate": PLATE,
            "vibration": {
                "psd_g2_hz": 0.01,
                "min_fn_hz": target,
                "parts": [
                    {
                        "ref": "U1",
                        "x_mm": 0,
                        "y_mm": 0,
                        "length_mm": 10,
                        "parallel_to": "width",
                        "steinberg_c": 1.0,
                    }
                ],
            },
        }
    )
    result = _by_id(run_ruggedness(section))["ruggedness.vibration.fn"]
    assert result.verdict == "fail"
    assert result.margin is not None and result.margin < 0
    lines = result.guidance or []
    for key in ("youngs_mpa", "component_mass_g", "thickness_mm"):
        fixed = plate.model_copy(update={key: _value(lines, key)})
        assert plate_natural_frequency(fixed) == pytest.approx(target, rel=1e-5)


def test_heavy_plate_reports_mass_cannot_fix_it() -> None:
    plate = RuggedPlate.model_validate({**PLATE, "component_mass_g": 0})
    target = plate_natural_frequency(plate) * 1.01
    section = RuggednessSection.model_validate(
        {
            "plate": {**PLATE, "component_mass_g": 0},
            "vibration": {
                "psd_g2_hz": 0.01,
                "min_fn_hz": target,
                "parts": [
                    {
                        "ref": "U1",
                        "x_mm": 0,
                        "y_mm": 0,
                        "length_mm": 10,
                        "parallel_to": "width",
                        "steinberg_c": 1.0,
                    }
                ],
            },
        }
    )
    lines = _by_id(run_ruggedness(section))["ruggedness.vibration.fn"].guidance or []
    assert any("bare plate" in line for line in lines)


def test_vibration_part_and_ingress_guidance() -> None:
    section = RuggednessSection.model_validate(
        {
            "plate": {**PLATE, "thickness_mm": 0.8},
            "vibration": {
                "psd_g2_hz": 0.5,
                "parts": [
                    {
                        "ref": "U1",
                        "x_mm": 0,
                        "y_mm": 0,
                        "length_mm": 30,
                        "parallel_to": "width",
                        "steinberg_c": 1.0,
                    }
                ],
            },
            "ingress": {"code": "IP4X", "openings_min_mm": [1.5], "sealed": False},
        }
    )
    checks = _by_id(run_ruggedness(section))
    part = checks["ruggedness.vibration.U1"]
    assert part.verdict == "fail"
    assert part.margin is not None and part.margin < 0
    assert _value(part.guidance or [], "psd_g2_hz") == pytest.approx(
        0.5 * ((part.margin + (part.measured or 0)) / (part.measured or 1)) ** 2, rel=1e-5
    )
    solids = checks["ruggedness.ingress.solids"]
    assert solids.verdict == "fail"
    assert solids.margin == pytest.approx(1.0 - 1.5)
    assert "1 mm" in (solids.guidance or [""])[0]


def test_non_finite_margin_drops_margin_and_guidance() -> None:
    item = check("x", "thermal", "fail", "d", measured=1.0, margin=float("nan"), guidance=["g"])
    assert item.margin is None
    assert item.to_dict()["guidance"] == []
