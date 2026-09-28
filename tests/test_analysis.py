from __future__ import annotations

import pytest

from sim import linalg
from sim.analysis import (
    branch_resistance,
    run_dft,
    run_emc,
    run_fem_analytic,
    run_pdn_rail,
    run_thermal,
    run_wca,
)
from sim.brief import (
    DebugHeader,
    Decap,
    Decoupling,
    DftSection,
    EmcDevice,
    EmcInterface,
    EmcProtection,
    EmcSection,
    EmcSignal,
    FemSection,
    PdnBranch,
    PdnLoad,
    PdnRail,
    TestPoint,
    ThermalSection,
    WcaSection,
)
from sim.gates import GateCheck


def _verdicts(checks: list[GateCheck]) -> dict[str, str]:
    return {item.id: item.verdict for item in checks}


def test_pdn_nodal_solve_and_limits() -> None:
    rail = PdnRail(
        name="VDD",
        source_v=5,
        max_drop_v=1,
        source_node="source",
        nodes=["source", "load"],
        branches=[
            PdnBranch(
                ref="R1",
                from_node="source",
                to_node="load",
                kind="resistor",
                resistance_ohm=1,
            )
        ],
        loads=[PdnLoad(node="load", current_a=1)],
    )

    assert _verdicts(run_pdn_rail(rail))["pdn.VDD.drop.load"] == "pass"
    assert (
        _verdicts(run_pdn_rail(rail.model_copy(update={"max_drop_v": 0.5})))["pdn.VDD.drop.load"]
        == "fail"
    )


def test_pdn_return_path_and_temperature_adjustment() -> None:
    branch = PdnBranch(
        ref="trace",
        from_node="source",
        to_node="load",
        kind="trace",
        length_mm=100,
        width_mm=1,
        copper_oz=1,
    )
    assert branch_resistance(branch, 100) > branch_resistance(branch, 20)
    rail = PdnRail(
        name="VDD",
        source_v=5,
        max_drop_v=0.21,
        source_node="source",
        return_source_node="ground",
        nodes=["source", "load", "return", "ground"],
        branches=[
            PdnBranch(
                ref="forward",
                from_node="source",
                to_node="load",
                kind="resistor",
                resistance_ohm=0.1,
            ),
            PdnBranch(
                ref="return",
                from_node="return",
                to_node="ground",
                kind="resistor",
                resistance_ohm=0.1,
            ),
        ],
        loads=[PdnLoad(node="load", current_a=1, return_node="return")],
    )

    assert _verdicts(run_pdn_rail(rail))["pdn.VDD.drop.load"] == "pass"
    resistance = branch_resistance(branch, 20)
    assert resistance == pytest.approx(0.0496, rel=0.003)
    assert branch_resistance(branch, 100) == pytest.approx(resistance * (1 + 0.00393 * 80))


def test_pdn_ipc2221_capacity_fails_for_excess_trace_current() -> None:
    rail = PdnRail(
        name="VDD",
        source_v=5,
        max_drop_v=1,
        source_node="source",
        nodes=["source", "load"],
        branches=[
            PdnBranch(
                ref="trace",
                from_node="source",
                to_node="load",
                kind="trace",
                length_mm=10,
                width_mm=0.1,
                thickness_um=17.5,
                layer="internal",
                allowed_rise_c=10,
            )
        ],
        loads=[PdnLoad(node="load", current_a=1)],
    )

    checks = _verdicts(run_pdn_rail(rail))

    assert checks["pdn.VDD.ampacity.trace"] == "fail"


def test_linear_solver_handles_known_system_and_rejects_singular_matrix() -> None:
    assert linalg.solve([[2.0, -1.0], [-1.0, 2.0]], [1.0, 0.0]) == pytest.approx([2 / 3, 1 / 3])
    with pytest.raises(ValueError, match="singular"):
        linalg.solve([[1.0, 1.0], [2.0, 2.0]], [1.0, 2.0])
    with pytest.raises(ValueError, match="non-finite"):
        linalg.solve([[float("inf")]], [1.0])


def test_thermal_path_and_resistance_network() -> None:
    scalar = ThermalSection.model_validate(
        {
            "ambient_c": 25,
            "components": [
                {
                    "ref": "U1",
                    "power_w": 2,
                    "tj_max_c": 60,
                    "path": {"theta_ja_c_per_w": 10},
                }
            ],
        }
    )
    assert _verdicts(run_thermal(scalar))["thermal.U1.tj"] == "pass"

    network = ThermalSection.model_validate(
        {
            "ambient_c": 25,
            "components": [{"ref": "U1", "power_w": 2, "tj_max_c": 60}],
            "network": {
                "nodes": ["ambient", "U1"],
                "resistances": [{"a": "U1", "b": "ambient", "c_per_w": 10}],
                "power_nodes": {"U1": 2},
                "ambient_node": "ambient",
            },
        }
    )
    assert _verdicts(run_thermal(network))["thermal.U1.tj"] == "pass"


def test_wca_is_deterministic_and_fail_closed() -> None:
    section = WcaSection.model_validate(
        {
            "parameters": [
                {"name": "R1", "nominal": 100, "tol_pct": 10},
                {"name": "R2", "nominal": 100, "tol_pct": 10},
            ],
            "outputs": [
                {"name": "ratio", "expression": "R2 / (R1 + R2)", "min": 0.45, "max": 0.55}
            ],
            "methods": ["EVA", "RSS", "MC"],
            "mc_samples": 100,
            "seed": 14,
        }
    )

    first = run_wca(section)
    second = run_wca(section)
    assert first == second
    assert _verdicts(first) == _verdicts(second)
    assert all(verdict == "pass" for verdict in _verdicts(first).values())
    assert (
        _verdicts(run_wca(section.model_copy(update={"max_vertices": 2})))["wca.EVA.ratio"]
        == "unknown"
    )


def test_emc_requires_one_protection_that_meets_every_limit() -> None:
    section = EmcSection(
        interfaces=[EmcInterface(connector_ref="J1", nets=["VIN"], esd_level=2, external=True)],
        protections=[
            EmcProtection(
                ref="D1",
                nets=["VIN"],
                vrwm_v=5,
                vclamp_v=10,
                esd_rating_contact_kv=8,
                distance_to_connector_mm=1,
            ),
            EmcProtection(
                ref="D2",
                nets=["VIN"],
                vrwm_v=12,
                vclamp_v=18,
                esd_rating_contact_kv=8,
                distance_to_connector_mm=1,
            ),
        ],
        protected_devices=[EmcDevice(ref="U1", nets=["VIN"], abs_max_v=20)],
        signals=[EmcSignal(net="VIN", v_max=12)],
        decoupling=[
            Decoupling(
                ic_ref="U1",
                power_pins=["VIN"],
                capacitors=[Decap(ref="C1", distance_mm=1)],
            )
        ],
    )

    assert _verdicts(run_emc(section))["emc.protection.J1.VIN"] == "pass"
    missing_facts = section.model_copy(
        update={"interfaces": [EmcInterface(connector_ref="J1", nets=["VIN"], external=True)]}
    )
    assert _verdicts(run_emc(missing_facts))["emc.protection.J1.VIN"] == "unknown"
    too_far = section.model_copy(update={"max_tvs_distance_mm": 0.5})
    assert _verdicts(run_emc(too_far))["emc.protection.J1.VIN"] == "fail"


def test_emc_signal_and_decoupling_rules_fail_or_remain_unknown() -> None:
    section = EmcSection.model_validate(
        {
            "signals": [
                {
                    "net": "CLK",
                    "v_max": 3.3,
                    "rise_time_ns": 0.1,
                    "length_mm": 50,
                    "high_speed": True,
                    "reference_plane_continuous": False,
                }
            ],
            "decoupling": [
                {
                    "ic_ref": "U1",
                    "power_pins": ["VDD"],
                    "capacitors": [{"ref": "C1", "distance_mm": 8}],
                }
            ],
        }
    )

    checks = _verdicts(run_emc(section))

    assert checks["emc.reference_plane.CLK"] == "fail"
    assert checks["emc.critical_length.CLK"] == "fail"
    assert checks["emc.decoupling.U1.VDD"] == "fail"
    incomplete = EmcSection.model_validate({"signals": [{"net": "CLK", "high_speed": True}]})
    incomplete_checks = _verdicts(run_emc(incomplete))
    assert incomplete_checks["emc.reference_plane.CLK"] == "unknown"
    assert incomplete_checks["emc.critical_length.CLK"] == "unknown"


def test_dft_and_fem_checks() -> None:
    section = DftSection(
        nets=["VIN"],
        required="all",
        test_points=[
            TestPoint(
                ref="TP1",
                net="VIN",
                pad_diameter_mm=1,
                x_mm=0,
                y_mm=0,
                side="top",
            )
        ],
        debug_header=DebugHeader(kind="swd", ref="J2"),
    )
    assert _verdicts(run_dft(section))["dft.coverage"] == "pass"
    assert (
        _verdicts(run_dft(section.model_copy(update={"debug_header": None})))["dft.debug_header"]
        == "fail"
    )
    failing_dft = section.model_copy(
        update={
            "test_points": [
                section.test_points[0].model_copy(update={"pad_diameter_mm": 0.5}),
                section.test_points[0].model_copy(update={"ref": "TP2", "x_mm": 0.5}),
            ],
            "bga_refs": ["U2"],
        }
    )
    failing_checks = _verdicts(run_dft(failing_dft))
    assert failing_checks["dft.pad_size"] == "fail"
    assert failing_checks["dft.pitch"] == "fail"
    assert failing_checks["dft.boundary_scan"] == "fail"

    fem = FemSection.model_validate(
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
        }
    )
    assert _verdicts(run_fem_analytic(fem))["fem.analytic.safety_factor"] == "pass"


@pytest.mark.parametrize("path", [{"mystery": 4}, {"theta_ja_c_per_w": -1}])
def test_thermal_path_schema_rejects_unsafe_values(path: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        ThermalSection.model_validate(
            {
                "ambient_c": 25,
                "components": [{"ref": "U1", "power_w": 1, "tj_max_c": 100, "path": path}],
            }
        )
