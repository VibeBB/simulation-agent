"""Boundary, decision-table and property tests for the deterministic gates.

Techniques follow docs/test-coverage.md: 3-value boundaries (below / on /
above, with ``math.nextafter`` for float limits), decision tables for
combined guards, and fail-closed cases where a gate cannot decide. Limits
that depend on a computed quantity are placed exactly on the measured
value, so the boundary is the gate's own comparison rather than a
re-derived formula.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

import pytest
from pydantic import ValidationError

from sim.analysis import (
    branch_resistance,
    microstrip_impedance,
    run_dft,
    run_emc,
    run_fem_analytic,
    run_pdn_rail,
    run_thermal,
    run_wca,
)
from sim.brief import (
    DftSection,
    EmcSection,
    EmcSignal,
    FemSection,
    PdnBranch,
    PdnLoad,
    PdnRail,
    RfBand,
    ThermalSection,
    WcaOutput,
    WcaSection,
)
from sim.gates import GateCheck, aggregate, check

UP = math.inf
DOWN = -math.inf


def _below(value: float) -> float:
    return math.nextafter(value, DOWN)


def _above(value: float) -> float:
    return math.nextafter(value, UP)


def _one(checks: list[GateCheck], check_id: str) -> GateCheck:
    [item] = [c for c in checks if c.id == check_id]
    return item


def _verdict(checks: list[GateCheck], check_id: str) -> str:
    return _one(checks, check_id).verdict


# ------------------------------------------------------------ gate core


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ([], "unknown"),
        (["pass"], "pass"),
        (["pass", "pass"], "pass"),
        (["pass", "unknown"], "unknown"),
        (["unknown", "fail"], "fail"),
        (["pass", "fail"], "fail"),
    ],
)
def test_aggregate_decision_table(verdicts: list[str], expected: str) -> None:
    checks = [check(f"c{i}", "x", v, "") for i, v in enumerate(verdicts)]  # pyright: ignore[reportArgumentType]
    assert aggregate(checks) == expected


@pytest.mark.parametrize(
    ("measured", "verdict"),
    [
        (None, "pass"),
        (1.0, "pass"),
        (math.inf, "unknown"),
        (-math.inf, "unknown"),
        (math.nan, "unknown"),
    ],
)
def test_non_finite_measurement_fails_closed(measured: float | None, verdict: str) -> None:
    assert check("c", "x", "pass", "", measured=measured).verdict == verdict


# ------------------------------------------------------------------ PDN


def _rail(**fields: Any) -> PdnRail:
    base: dict[str, Any] = {
        "name": "VDD",
        "source_v": 5,
        "max_drop_v": 1,
        "source_node": "source",
        "nodes": ["source", "load"],
        "branches": [
            {
                "ref": "R1",
                "from_node": "source",
                "to_node": "load",
                "kind": "resistor",
                "resistance_ohm": 1,
            }
        ],
        "loads": [{"node": "load", "current_a": 1}],
    }
    return PdnRail.model_validate({**base, **fields})


# Drop is exactly 1.0 V; the gate allows a 1e-12 V solver tolerance.
@pytest.mark.parametrize(
    ("limit", "verdict"),
    [(1.0 - 2e-12, "fail"), (1.0 - 0.5e-12, "pass"), (1.0, "pass"), (_above(1.0), "pass")],
)
def test_pdn_drop_boundary(limit: float, verdict: str) -> None:
    assert _verdict(run_pdn_rail(_rail(max_drop_v=limit)), "pdn.VDD.drop.load") == verdict


# max_drop_v x max_drop_pct x min_v: the tightest limit wins.
@pytest.mark.parametrize(
    ("fields", "verdict"),
    [
        ({"max_drop_v": None, "max_drop_pct": 20}, "pass"),
        ({"max_drop_v": None, "max_drop_pct": 19.9}, "fail"),
        ({"max_drop_v": 2, "max_drop_pct": 19.9}, "fail"),
        ({"max_drop_v": 0.9, "max_drop_pct": 50}, "fail"),
        ({"max_drop_v": 2, "loads": [{"node": "load", "current_a": 1, "min_v": 4}]}, "pass"),
        ({"max_drop_v": 2, "loads": [{"node": "load", "current_a": 1, "min_v": 4.01}]}, "fail"),
    ],
)
def test_pdn_limit_combinations(fields: dict[str, Any], verdict: str) -> None:
    assert _verdict(run_pdn_rail(_rail(**fields)), "pdn.VDD.drop.load") == verdict


def _measured_then_limit(branch: dict[str, Any], key: str) -> list[str]:
    def rail(value: float | None) -> PdnRail:
        b = {**branch, key: value} if value is not None else dict(branch)
        return _rail(max_drop_v=5, branches=[b])

    measured = _one(run_pdn_rail(rail(1000.0)), "pdn.VDD.ampacity.W1").measured
    assert measured is not None and measured > 0
    return [
        _verdict(run_pdn_rail(rail(value)), "pdn.VDD.ampacity.W1")
        for value in (_below(measured), measured, _above(measured))
    ]


def test_wire_ampacity_three_value_boundary() -> None:
    wire = {
        "ref": "W1",
        "from_node": "source",
        "to_node": "load",
        "kind": "wire",
        "length_m": 1,
        "resistance_ohm_per_km": 100,
    }
    assert _measured_then_limit(wire, "ampacity_a") == ["fail", "pass", "pass"]


def test_via_ampacity_three_value_boundary() -> None:
    via = {
        "ref": "W1",
        "from_node": "source",
        "to_node": "load",
        "kind": "via",
        "count": 2,
        "drill_mm": 0.3,
        "length_mm": 1.6,
    }
    assert _measured_then_limit(via, "via_max_a") == ["fail", "pass", "pass"]


def test_ampacity_is_not_checked_without_a_rating() -> None:
    wire = {
        "ref": "W1",
        "from_node": "source",
        "to_node": "load",
        "kind": "wire",
        "length_m": 1,
        "resistance_ohm_per_km": 100,
    }
    checks = run_pdn_rail(_rail(max_drop_v=5, branches=[wire]))
    assert [c.id for c in checks] == ["pdn.VDD.drop.load"]


def test_load_on_source_node_is_rejected_by_the_schema() -> None:
    with pytest.raises(ValidationError, match="fixed source node"):
        _rail(loads=[{"node": "source", "current_a": 1}])


def test_floating_node_fails_closed() -> None:
    checks = run_pdn_rail(_rail(nodes=["source", "load", "island"]))
    assert [c.verdict for c in checks] == ["unknown"]


# Copper resistance reaches zero at 20 - 1/alpha degrees C.
@pytest.mark.parametrize(("temperature", "ok"), [(-300.0, False), (-234.0, True), (20.0, True)])
def test_copper_resistance_positive_domain(temperature: float, ok: bool) -> None:
    wire = PdnBranch(
        ref="W1", from_node="a", to_node="b", kind="wire", length_m=1, resistance_ohm_per_km=100
    )
    if ok:
        assert branch_resistance(wire, temperature) > 0
    else:
        with pytest.raises(ValueError, match="non-positive"):
            branch_resistance(wire, temperature)


@pytest.mark.parametrize(("current", "ok"), [(-1e-9, False), (0.0, True), (1e-9, True)])
def test_load_current_sign_boundary(current: float, ok: bool) -> None:
    if ok:
        PdnLoad(node="n", current_a=current)
    else:
        with pytest.raises(ValidationError):
            PdnLoad(node="n", current_a=current)


# -------------------------------------------------------------- thermal


def _thermal(
    tj_max: float, margin: float = 0.0, path: dict[str, float] | None = None
) -> ThermalSection:
    return ThermalSection.model_validate(
        {
            "ambient_c": 25,
            "components": [
                {
                    "ref": "U1",
                    "power_w": 2,
                    "tj_max_c": tj_max,
                    "derating_margin_c": margin,
                    "path": path or {"theta_ja_c_per_w": 10},
                }
            ],
        }
    )


# Tj = 25 + 2 W x 10 C/W = 45 C exactly.
@pytest.mark.parametrize(
    ("tj_max", "verdict"), [(_below(45.0), "fail"), (45.0, "pass"), (_above(45.0), "pass")]
)
def test_junction_temperature_three_value_boundary(tj_max: float, verdict: str) -> None:
    assert _verdict(run_thermal(_thermal(tj_max)), "thermal.U1.tj") == verdict


@pytest.mark.parametrize(("margin", "verdict"), [(4.99, "pass"), (5.0, "pass"), (5.01, "fail")])
def test_derating_margin_three_value_boundary(margin: float, verdict: str) -> None:
    assert _verdict(run_thermal(_thermal(50.0, margin)), "thermal.U1.tj") == verdict


@pytest.mark.parametrize(
    ("path", "verdict"),
    [
        ({"theta_jc": 4, "theta_sa": 6}, "pass"),
        ({"theta_jc": 4, "theta_cs": 0.5, "theta_sa": 6}, "fail"),
        ({"theta_jc": 4}, "unknown"),
        ({"theta_sa": 6}, "unknown"),
        ({"theta_ja_c_per_w": 0}, "pass"),
    ],
)
def test_series_thermal_path(path: dict[str, float], verdict: str) -> None:
    assert _verdict(run_thermal(_thermal(45.0, path=path)), "thermal.U1.tj") == verdict


def test_thermal_without_path_or_components_is_unknown() -> None:
    no_path = ThermalSection.model_validate(
        {"ambient_c": 25, "components": [{"ref": "U1", "power_w": 1, "tj_max_c": 100}]}
    )
    assert _verdict(run_thermal(no_path), "thermal.U1.tj") == "unknown"
    empty = ThermalSection.model_validate({"ambient_c": 25})
    assert [(c.id, c.verdict) for c in run_thermal(empty)] == [("thermal.components", "unknown")]


def _network(components: list[dict[str, Any]], power: dict[str, float]) -> ThermalSection:
    return ThermalSection.model_validate(
        {
            "ambient_c": 25,
            "components": components,
            "network": {
                "nodes": ["ambient", "U1"],
                "resistances": [{"a": "U1", "b": "ambient", "c_per_w": 10}],
                "power_nodes": power,
                "ambient_node": "ambient",
            },
        }
    )


@pytest.mark.parametrize(
    ("tj_max", "verdict"), [(_below(45.0), "fail"), (45.0, "pass"), (_above(45.0), "pass")]
)
def test_network_junction_three_value_boundary(tj_max: float, verdict: str) -> None:
    section = _network([{"ref": "U1", "power_w": 2, "tj_max_c": tj_max}], {"U1": 2})
    assert _verdict(run_thermal(section), "thermal.U1.tj") == verdict


def test_network_mapping_gaps_fail_closed() -> None:
    unpowered = _network(
        [
            {"ref": "U1", "power_w": 2, "tj_max_c": 100},
            {"ref": "U2", "power_w": 1, "tj_max_c": 100},
        ],
        {"U1": 2},
    )
    assert _verdict(run_thermal(unpowered), "thermal.U2.tj") == "unknown"
    assert _verdict(run_thermal(unpowered), "thermal.U1.tj") == "pass"


# ------------------------------------------------------------------ WCA


def _wca(**output: Any) -> WcaSection:
    return WcaSection.model_validate(
        {
            "parameters": [{"name": "R", "nominal": 1.0, "tol_abs": 0.5}],
            "outputs": [{"name": "out", "expression": "R", **output}],
            "methods": ["EVA"],
        }
    )


# EVA over R = 1 +/- 0.5 gives exactly [0.5, 1.5].
@pytest.mark.parametrize(
    ("bounds", "verdict"),
    [
        ({"min": 0.5}, "pass"),
        ({"min": _above(0.5)}, "fail"),
        ({"min": _below(0.5)}, "pass"),
        ({"max": 1.5}, "pass"),
        ({"max": _below(1.5)}, "fail"),
        ({"max": _above(1.5)}, "pass"),
        ({"min": 0.5, "max": 1.5}, "pass"),
        ({}, "unknown"),
    ],
)
def test_wca_output_window_three_value_boundary(bounds: dict[str, float], verdict: str) -> None:
    assert _verdict(run_wca(_wca(**bounds)), "wca.EVA.out") == verdict


@pytest.mark.parametrize(("max_vertices", "verdict"), [(1, "unknown"), (2, "pass"), (3, "pass")])
def test_wca_vertex_budget_boundary(max_vertices: int, verdict: str) -> None:
    section = _wca(min=0.5).model_copy(update={"max_vertices": max_vertices})
    assert _verdict(run_wca(section), "wca.EVA.out") == verdict


def test_wca_temperature_coefficient_widens_the_tolerance() -> None:
    section = WcaSection.model_validate(
        {
            "parameters": [
                {
                    "name": "R",
                    "nominal": 100,
                    "tol_abs": 1,
                    "temp_coeff_ppm": 100,
                    "temp_range_c": 50,
                }
            ],
            "outputs": [{"name": "out", "expression": "R", "min": 98.5, "max": 101.5}],
            "methods": ["EVA"],
        }
    )
    item = _one(run_wca(section), "wca.EVA.out")
    assert item.verdict == "pass"
    assert item.measured == pytest.approx(98.5)


def test_wca_expression_failure_is_unknown() -> None:
    section = WcaSection.model_validate(
        {
            "parameters": [{"name": "R", "nominal": 1.0, "tol_abs": 0.5}],
            "outputs": [{"name": "out", "expression": "R / (R - R)", "max": 1}],
            "methods": ["EVA", "RSS"],
        }
    )
    assert {c.verdict for c in run_wca(section)} == {"unknown"}


@pytest.mark.parametrize(
    ("low", "high", "ok"), [(1.0, 1.0, True), (_above(1.0), 1.0, False), (0.0, 1.0, True)]
)
def test_wca_output_bounds_order(low: float, high: float, ok: bool) -> None:
    payload = {"name": "out", "expression": "R", "min": low, "max": high}
    if ok:
        WcaOutput.model_validate(payload)
    else:
        with pytest.raises(ValidationError):
            WcaOutput.model_validate(payload)


@pytest.mark.parametrize(("f_max", "ok"), [(_below(1e6), False), (1e6, False), (_above(1e6), True)])
def test_rf_band_order(f_max: float, ok: bool) -> None:
    payload = {"name": "b", "f_min_hz": 1e6, "f_max_hz": f_max}
    if ok:
        RfBand.model_validate(payload)
    else:
        with pytest.raises(ValidationError):
            RfBand.model_validate(payload)


# ------------------------------------------------------------------ EMC


def _emc(
    *,
    esd_level: int | None = 2,
    vrwm: float = 12,
    rating: float = 8,
    distance: float = 1,
    vclamp: float = 18,
    device: bool = True,
    v_max: float | None = 12,
    external: bool = True,
) -> list[GateCheck]:
    interface: dict[str, Any] = {"connector_ref": "J1", "nets": ["VIN"], "external": external}
    if esd_level is not None:
        interface["esd_level"] = esd_level
    signal: dict[str, Any] = {"net": "VIN"}
    if v_max is not None:
        signal["v_max"] = v_max
    section = EmcSection.model_validate(
        {
            "interfaces": [interface],
            "protections": [
                {
                    "ref": "D1",
                    "nets": ["VIN"],
                    "vrwm_v": vrwm,
                    "vclamp_v": vclamp,
                    "esd_rating_contact_kv": rating,
                    "distance_to_connector_mm": distance,
                }
            ],
            "protected_devices": [{"ref": "U1", "nets": ["VIN"], "abs_max_v": 20}]
            if device
            else [],
            "signals": [signal],
        }
    )
    return run_emc(section)


PROTECTION = "emc.protection.J1.VIN"


# MC/DC for the four protection rules: each rule flips the verdict alone.
@pytest.mark.parametrize(
    ("fields", "verdict"),
    [
        ({}, "pass"),
        ({"vrwm": _below(12.0)}, "fail"),
        ({"rating": _below(4.0)}, "fail"),
        ({"rating": 4.0}, "pass"),
        ({"distance": 10.0}, "pass"),
        ({"distance": _above(10.0)}, "fail"),
        ({"vclamp": 20.0}, "pass"),
        ({"vclamp": _above(20.0)}, "fail"),
        ({"esd_level": None}, "unknown"),
        ({"device": False}, "unknown"),
        ({"v_max": None}, "unknown"),
    ],
)
def test_protection_rule_decision_table(fields: dict[str, Any], verdict: str) -> None:
    assert _verdict(_emc(**fields), PROTECTION) == verdict


@pytest.mark.parametrize(("level", "required"), [(1, 2.0), (2, 4.0), (3, 6.0), (4, 8.0)])
def test_esd_level_contact_rating_boundaries(level: int, required: float) -> None:
    assert _verdict(_emc(esd_level=level, rating=required), PROTECTION) == "pass"
    assert _verdict(_emc(esd_level=level, rating=_below(required)), PROTECTION) == "fail"


def test_internal_interfaces_are_not_checked() -> None:
    assert [c.id for c in _emc(external=False)] == ["emc.inputs"]


def test_unprotected_external_net_fails() -> None:
    section = EmcSection.model_validate(
        {"interfaces": [{"connector_ref": "J1", "nets": ["VIN"], "external": True}]}
    )
    assert _verdict(run_emc(section), PROTECTION) == "fail"


def _critical_mm(rise_ns: float) -> float:
    er_eff = EmcSignal(net="X").er_eff
    assert er_eff is not None
    return rise_ns * 1e-9 * 299_792_458 / math.sqrt(er_eff) / 6 * 1000


@pytest.mark.parametrize(
    ("offset", "terminated", "verdict"),
    [(DOWN, False, "pass"), (0, False, "pass"), (UP, False, "fail"), (UP, True, "pass")],
)
def test_critical_length_three_value_boundary(
    offset: float, terminated: bool, verdict: str
) -> None:
    critical = _critical_mm(1.0)
    length = critical if offset == 0 else math.nextafter(critical, offset)
    section = EmcSection.model_validate(
        {
            "signals": [
                {"net": "S", "length_mm": length, "rise_time_ns": 1.0, "terminated": terminated}
            ]
        }
    )
    assert _verdict(run_emc(section), "emc.critical_length.S") == verdict


@pytest.mark.parametrize(
    ("continuous", "verdicts"), [(None, ["unknown"]), (False, ["fail"]), (True, [])]
)
def test_reference_plane_decision_table(continuous: bool | None, verdicts: list[str]) -> None:
    signal: dict[str, Any] = {"net": "CLK", "high_speed": True}
    if continuous is not None:
        signal["reference_plane_continuous"] = continuous
    checks = run_emc(EmcSection.model_validate({"signals": [signal]}))
    assert [c.verdict for c in checks if c.id == "emc.reference_plane.CLK"] == verdicts


@pytest.mark.parametrize(
    ("caps", "distance", "verdict"),
    [
        (1, 1.0, "fail"),
        (2, 1.0, "pass"),
        (3, 1.0, "pass"),
        (2, 5.0, "pass"),
        (2, _above(5.0), "fail"),
    ],
)
def test_decoupling_count_and_distance(caps: int, distance: float, verdict: str) -> None:
    section = EmcSection.model_validate(
        {
            "min_caps_per_pin": 2,
            "decoupling": [
                {
                    "ic_ref": "U1",
                    "power_pins": ["VDD"],
                    "capacitors": [
                        {"ref": f"C{i}", "distance_mm": distance if i == 0 else 1.0}
                        for i in range(caps)
                    ],
                }
            ],
        }
    )
    assert _verdict(run_emc(section), "emc.decoupling.U1.VDD") == verdict


# ------------------------------------------------------------------ DFT


def _dft(**fields: Any) -> DftSection:
    base: dict[str, Any] = {
        "nets": ["A", "B", "C", "D"],
        "required": "all",
        "test_points": [
            {
                "ref": f"TP{i}",
                "net": net,
                "pad_diameter_mm": 1.0,
                "x_mm": 10.0 * i,
                "y_mm": 0,
                "side": "top",
            }
            for i, net in enumerate(["A", "B", "C"])
        ],
        "debug_header": {"kind": "swd", "ref": "J2"},
    }
    return DftSection.model_validate({**base, **fields})


@pytest.mark.parametrize(("minimum", "verdict"), [(0.74, "pass"), (0.75, "pass"), (0.76, "fail")])
def test_dft_coverage_three_value_boundary(minimum: float, verdict: str) -> None:
    assert _verdict(run_dft(_dft(min_coverage=minimum)), "dft.coverage") == verdict


@pytest.mark.parametrize(
    ("required", "critical", "verdict"),
    [
        ("all", [], "fail"),
        ("listed", ["A", "B"], "pass"),
        ("listed", [], "fail"),
        ("power_and_critical", ["A"], "fail"),
    ],
)
def test_dft_required_set_decision_table(required: str, critical: list[str], verdict: str) -> None:
    section = _dft(required=required, critical_nets=critical)
    assert _verdict(run_dft(section), "dft.coverage") == verdict


def test_dft_without_required_nets_is_unknown() -> None:
    checks = run_dft(_dft(nets=[], test_points=[]))
    assert _verdict(checks, "dft.coverage") == "unknown"
    assert _verdict(checks, "dft.pad_size") == "unknown"
    assert _verdict(checks, "dft.pitch") == "unknown"


@pytest.mark.parametrize(
    ("pad", "verdict"), [(_below(0.9), "fail"), (0.9, "pass"), (_above(0.9), "pass")]
)
def test_dft_pad_three_value_boundary(pad: float, verdict: str) -> None:
    points = [
        {"ref": "TP0", "net": "A", "pad_diameter_mm": pad, "x_mm": 0, "y_mm": 0, "side": "top"}
    ]
    assert _verdict(run_dft(_dft(test_points=points)), "dft.pad_size") == verdict


@pytest.mark.parametrize(
    ("x", "side", "verdict"),
    [
        (_below(2.54), "top", "fail"),
        (2.54, "top", "pass"),
        (_above(2.54), "top", "pass"),
        (0.1, "bottom", "pass"),
    ],
)
def test_dft_pitch_three_value_boundary(x: float, side: str, verdict: str) -> None:
    points = [
        {"ref": "TP0", "net": "A", "pad_diameter_mm": 1, "x_mm": 0, "y_mm": 0, "side": "top"},
        {"ref": "TP1", "net": "B", "pad_diameter_mm": 1, "x_mm": x, "y_mm": 0, "side": side},
    ]
    assert _verdict(run_dft(_dft(test_points=points)), "dft.pitch") == verdict


@pytest.mark.parametrize(
    ("fields", "statuses"),
    [
        ({}, ["pass"]),
        ({"debug_header": None}, ["fail"]),
        ({"debug_header": {"kind": "none", "ref": "J2"}}, ["fail"]),
        ({"debug_header": None, "require_debug_header": False}, []),
    ],
)
def test_dft_debug_header_decision_table(fields: dict[str, Any], statuses: list[str]) -> None:
    checks = run_dft(_dft(**fields))
    assert [c.verdict for c in checks if c.id == "dft.debug_header"] == statuses


@pytest.mark.parametrize(
    ("bga", "chain", "statuses"),
    [([], False, []), (["U2"], False, ["fail"]), (["U2"], True, ["pass"])],
)
def test_dft_boundary_scan_decision_table(bga: list[str], chain: bool, statuses: list[str]) -> None:
    checks = run_dft(_dft(bga_refs=bga, boundary_scan_chain=chain))
    assert [c.verdict for c in checks if c.id == "dft.boundary_scan"] == statuses


# ------------------------------------------------------------------ FEM


def _fem(min_sf: float = 2.0) -> FemSection:
    return FemSection.model_validate(
        {
            "geometry": {
                "kind": "cantilever_box",
                "length_mm": 100,
                "width_mm": 10,
                "height_mm": 10,
            },
            "material": {
                "name": "aluminum",
                "youngs_mpa": 70000,
                "poisson": 0.33,
                "yield_mpa": 240,
            },
            "load": {"kind": "tip_force", "force_n": 10, "direction": "-z"},
            "mesh": {"nx": 2, "ny": 1, "nz": 1, "element": "C3D8I"},
            "limits": {"min_safety_factor": min_sf},
        }
    )


def test_fem_safety_factor_three_value_boundary() -> None:
    measured = _one(run_fem_analytic(_fem()), "fem.analytic.safety_factor").measured
    assert measured is not None
    assert measured == pytest.approx(40.0)
    verdicts = [
        _verdict(run_fem_analytic(_fem(limit)), "fem.analytic.safety_factor")
        for limit in (_below(measured), measured, _above(measured))
    ]
    assert verdicts == ["pass", "pass", "fail"]


# ------------------------------------------------------------ microstrip


def test_microstrip_impedance_decreases_with_width_across_both_branches() -> None:
    widths = [0.05 * step for step in range(2, 120)]  # w/h from 0.1 to 6 crosses w/h = 1
    values = [microstrip_impedance(width, 1.0, 35.0, 4.3) for width in widths]
    assert all(later < earlier for earlier, later in itertools.pairwise(values))
    assert all(math.isfinite(value) and value > 0 for value in values)
