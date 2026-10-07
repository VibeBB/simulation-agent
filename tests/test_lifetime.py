from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from sim.analysis import arrhenius_life_h, lifetime_guidance, run_lifetime
from sim.brief import LifetimePart, LifetimeSection, SimulationBrief


def _part(**overrides: object) -> LifetimePart:
    raw: dict[str, object] = {
        "ref": "C1",
        "rated_life_h": 2000.0,
        "rated_temp_c": 105.0,
        "activation_energy_ev": 0.94,
        "profile": [{"temperature_c": 65.0, "fraction": 1.0}],
        "required_life_h": 40000.0,
        "source": "datasheet UHE series p.3",
    }
    raw.update(overrides)
    return LifetimePart.model_validate(raw)


def test_single_step_matches_closed_form_arrhenius() -> None:
    part = _part()
    factor = math.exp(0.94 / 8.617333262e-5 * (1 / 338.15 - 1 / 378.15))
    assert arrhenius_life_h(part) == pytest.approx(2000.0 * factor)


def test_rated_temperature_gives_rated_life() -> None:
    part = _part(profile=[{"temperature_c": 105.0, "fraction": 1.0}])
    assert arrhenius_life_h(part) == pytest.approx(2000.0)


def test_miner_rule_combines_profile_steps() -> None:
    hot = _part(profile=[{"temperature_c": 85.0, "fraction": 1.0}])
    cool = _part(profile=[{"temperature_c": 45.0, "fraction": 1.0}])
    mixed = _part(
        profile=[
            {"temperature_c": 85.0, "fraction": 0.25},
            {"temperature_c": 45.0, "fraction": 0.75},
        ]
    )
    expected = 1 / (0.25 / arrhenius_life_h(hot) + 0.75 / arrhenius_life_h(cool))
    assert arrhenius_life_h(mixed) == pytest.approx(expected)


def test_passing_and_failing_checks() -> None:
    section = LifetimeSection.model_validate(
        {
            "parts": [
                _part().model_dump(),
                _part(ref="C2", profile=[{"temperature_c": 95.0, "fraction": 1.0}]).model_dump(),
            ]
        }
    )
    first, second = run_lifetime(section)
    assert (first.id, first.verdict) == ("lifetime.C1.life_h", "pass")
    assert first.limit == "≥ 40000 h"
    assert "fix:" not in first.detail
    assert (second.id, second.verdict) == ("lifetime.C2.life_h", "fail")
    assert "margin -" in second.detail
    assert "lower every profile temperature by" in second.detail


def test_guidance_inverts_to_the_requirement() -> None:
    part = _part(
        profile=[
            {"temperature_c": 95.0, "fraction": 0.5},
            {"temperature_c": 75.0, "fraction": 0.5},
        ]
    )
    life = arrhenius_life_h(part)
    lines = lifetime_guidance(part, life)
    cooling = next(line for line in lines if line.startswith("lower every"))
    shift = float(cooling.split("≥ ")[1].split(" ")[0])
    assert arrhenius_life_h(part, -shift) == pytest.approx(40000.0, rel=1e-4)
    rated = next(line for line in lines if line.startswith("rated_life_h"))
    needed = float(rated.split("≥ ")[1].split(" ")[0])
    assert arrhenius_life_h(_part(rated_life_h=needed, profile=part.model_dump()["profile"])) == (
        pytest.approx(40000.0, rel=1e-4)
    )


def test_overflowing_factor_is_unknown() -> None:
    section = LifetimeSection.model_validate(
        {
            "parts": [
                _part(
                    activation_energy_ev=1e6,
                    profile=[{"temperature_c": -270.0, "fraction": 1.0}],
                ).model_dump()
            ]
        }
    )
    (result,) = run_lifetime(section)
    assert result.verdict == "unknown"


@pytest.mark.parametrize(
    "overrides",
    [
        {"profile": [{"temperature_c": 65.0, "fraction": 0.5}]},
        {"profile": []},
        {"activation_energy_ev": 0},
        {"rated_life_h": 0},
        {"required_life_h": -1},
        {"source": ""},
        {"rated_temp_c": -300},
    ],
)
def test_invalid_parts_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _part(**overrides)


def test_duplicate_refs_are_rejected_and_section_counts_as_analysis() -> None:
    with pytest.raises(ValidationError):
        LifetimeSection.model_validate({"parts": [_part().model_dump(), _part().model_dump()]})
    brief = SimulationBrief.model_validate(
        {"schema_version": 1, "name": "cap", "lifetime": {"parts": [_part().model_dump()]}}
    )
    assert brief.lifetime is not None
