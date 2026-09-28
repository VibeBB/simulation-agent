"""Built-in deterministic analysis methods."""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Callable
from typing import cast

from . import expr, linalg
from .brief import (
    DftSection,
    EmcProtection,
    EmcSection,
    FemSection,
    PdnBranch,
    PdnRail,
    TestPoint,
    ThermalSection,
    WcaSection,
)
from .gates import GateCheck, check

COPPER_RHO = 1.724e-8
COPPER_ALPHA = 0.00393
OZ_COPPER_UM = 34.79


def branch_resistance(branch: PdnBranch, temperature_c: float) -> float:
    if branch.kind == "resistor":
        value = cast(float, branch.resistance_ohm)
    elif branch.kind == "wire":
        value = cast(float, branch.length_m) / 1000 * cast(float, branch.resistance_ohm_per_km)
    elif branch.kind == "via":
        length_m = (branch.length_mm or 1.6) / 1000
        drill_m = cast(float, branch.drill_mm) / 1000
        plating_m = branch.plating_um / 1_000_000
        area = math.pi * ((drill_m / 2 + plating_m) ** 2 - (drill_m / 2) ** 2)
        value = COPPER_RHO * length_m / (area * cast(int, branch.count))
    else:
        length_m = cast(float, branch.length_mm) / 1000
        width_m = cast(float, branch.width_mm) / 1000
        thickness_um = branch.thickness_um
        if thickness_um is None and branch.copper_oz is not None:
            thickness_um = branch.copper_oz * OZ_COPPER_UM
        thickness_m = (thickness_um or OZ_COPPER_UM) / 1_000_000
        value = COPPER_RHO * length_m / (width_m * thickness_m)
    if branch.kind != "resistor":
        value *= 1 + COPPER_ALPHA * (temperature_c - 20)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"branch {branch.ref} has non-positive or non-finite resistance")
    return value


def run_pdn_rail(rail: PdnRail) -> list[GateCheck]:
    try:
        fixed = {rail.source_node: rail.source_v}
        if rail.return_source_node is not None:
            fixed[rail.return_source_node] = 0.0
        unknown = [node for node in rail.nodes if node not in fixed]
        indices = {node: index for index, node in enumerate(unknown)}
        matrix = [[0.0 for _ in unknown] for _ in unknown]
        rhs = [0.0 for _ in unknown]
        resistances = {b.ref: branch_resistance(b, rail.temperature_c) for b in rail.branches}
        for branch in rail.branches:
            conductance = 1 / resistances[branch.ref]
            a, b = branch.from_node, branch.to_node
            for node, other in ((a, b), (b, a)):
                if node not in indices:
                    continue
                i = indices[node]
                matrix[i][i] += conductance
                if other in indices:
                    matrix[i][indices[other]] -= conductance
                else:
                    rhs[i] += conductance * fixed[other]
        loads: dict[str, float] = {}
        for load in rail.loads:
            if not isinstance(load.current_a, (int, float)):
                raise ValueError(f"unresolved imported current for {load.node}")
            loads[load.node] = loads.get(load.node, 0.0) + float(load.current_a)
        for node, current in loads.items():
            if node == rail.source_node:
                raise ValueError("loads cannot be attached directly to source_node")
            rhs[indices[node]] -= current
        for load in rail.loads:
            if load.return_node is not None and load.return_node != rail.return_source_node:
                rhs[indices[load.return_node]] += float(load.current_a)
        voltages = dict(fixed)
        voltages.update(zip(unknown, linalg.solve(matrix, rhs), strict=True))
        checks: list[GateCheck] = []
        for load in rail.loads:
            voltage = voltages[load.node] - (
                voltages[load.return_node] if load.return_node is not None else 0.0
            )
            limits: list[float] = []
            if rail.max_drop_v is not None:
                limits.append(rail.max_drop_v)
            if rail.max_drop_pct is not None:
                limits.append(rail.source_v * rail.max_drop_pct / 100)
            limit = min(limits)
            drop = rail.source_v - voltage
            required = load.min_v
            if required is not None:
                limit = min(limit, rail.source_v - required)
            checks.append(
                check(
                    f"pdn.{rail.name}.drop.{load.node}",
                    "pdn",
                    "pass" if drop <= limit + 1e-12 else "fail",
                    f"load voltage {voltage:.9g} V; drop {drop:.9g} V",
                    measured=drop,
                    limit=f"≤ {limit:.9g} V",
                )
            )
        for branch in rail.branches:
            current = (
                abs(voltages[branch.from_node] - voltages[branch.to_node]) / resistances[branch.ref]
            )
            if branch.kind == "trace":
                thickness_um = branch.thickness_um or (
                    branch.copper_oz * OZ_COPPER_UM if branch.copper_oz else OZ_COPPER_UM
                )
                area_mil2 = (cast(float, branch.width_mm) * 1000 / 25.4) * (thickness_um / 25.4)
                k = 0.048 if branch.layer == "external" else 0.024
                capacity = k * branch.allowed_rise_c**0.44 * area_mil2**0.725
                checks.append(
                    check(
                        f"pdn.{rail.name}.ampacity.{branch.ref}",
                        "pdn",
                        "pass" if current <= capacity + 1e-12 else "fail",
                        f"branch current {current:.9g} A; IPC-2221 capacity {capacity:.9g} A",
                        measured=current,
                        limit=f"≤ {capacity:.9g} A",
                    )
                )
            elif branch.kind == "via" and branch.via_max_a is not None:
                each_current = current / cast(int, branch.count)
                checks.append(
                    check(
                        f"pdn.{rail.name}.ampacity.{branch.ref}",
                        "pdn",
                        "pass" if each_current <= branch.via_max_a else "fail",
                        f"per-via current {each_current:.9g} A",
                        measured=each_current,
                        limit=f"≤ {branch.via_max_a:.9g} A",
                    )
                )
            elif branch.kind == "wire" and branch.ampacity_a is not None:
                checks.append(
                    check(
                        f"pdn.{rail.name}.ampacity.{branch.ref}",
                        "pdn",
                        "pass" if current <= branch.ampacity_a else "fail",
                        f"wire current {current:.9g} A",
                        measured=current,
                        limit=f"≤ {branch.ampacity_a:.9g} A",
                    )
                )
        return checks
    except (ArithmeticError, KeyError, ValueError) as exc:
        return [
            check(
                f"pdn.{rail.name}.network",
                "pdn",
                "unknown",
                f"network could not be solved: {exc}",
            )
        ]


def run_thermal(section: ThermalSection) -> list[GateCheck]:
    results: list[GateCheck] = []
    if section.network is None:
        for component in section.components:
            path = (
                component.path.model_dump(exclude_none=True) if component.path is not None else {}
            )
            theta = path.get("theta_ja_c_per_w")
            if theta is None:
                if "theta_jc" not in path or "theta_sa" not in path:
                    results.append(
                        check(
                            f"thermal.{component.ref}.tj",
                            "thermal",
                            "unknown",
                            "missing complete thermal resistance path",
                        )
                    )
                    continue
                series = [path["theta_jc"], path.get("theta_cs", 0.0), path["theta_sa"]]
                theta = sum(series)
            if not math.isfinite(theta) or theta < 0:
                results.append(
                    check(
                        f"thermal.{component.ref}.tj",
                        "thermal",
                        "unknown",
                        "thermal resistance must be finite and non-negative",
                    )
                )
                continue
            temp = section.ambient_c + component.power_w * theta
            limit = component.tj_max_c - component.derating_margin_c
            results.append(
                check(
                    f"thermal.{component.ref}.tj",
                    "thermal",
                    "pass" if temp <= limit else "fail",
                    f"junction temperature {temp:.9g} °C",
                    measured=temp,
                    limit=f"≤ {limit:.9g} °C",
                )
            )
    else:
        network = section.network
        try:
            unknown = [node for node in network.nodes if node != network.ambient_node]
            if (
                network.ambient_node not in network.nodes
                or len(set(network.nodes)) != len(network.nodes)
                or any(
                    resistance.a not in network.nodes or resistance.b not in network.nodes
                    for resistance in network.resistances
                )
            ):
                raise ValueError("network references an undeclared or duplicate node")
            indexes = {node: i for i, node in enumerate(unknown)}
            matrix = [[0.0 for _ in unknown] for _ in unknown]
            rhs = [0.0 for _ in unknown]
            for resistance in network.resistances:
                conductance = 1 / resistance.c_per_w
                for node, other in ((resistance.a, resistance.b), (resistance.b, resistance.a)):
                    if node not in indexes:
                        continue
                    i = indexes[node]
                    matrix[i][i] += conductance
                    if other in indexes:
                        matrix[i][indexes[other]] -= conductance
            for node, power in network.power_nodes.items():
                if node not in indexes:
                    raise ValueError(f"unknown power node {node!r}")
                if not math.isfinite(power) or power < 0:
                    raise ValueError(f"invalid power value for {node!r}")
                rhs[indexes[node]] += power
            temps = dict(
                zip(
                    unknown,
                    (section.ambient_c + delta for delta in linalg.solve(matrix, rhs)),
                    strict=True,
                )
            )
            components = {component.ref: component for component in section.components}
            for component in section.components:
                if component.ref not in network.power_nodes:
                    results.append(
                        check(
                            f"thermal.{component.ref}.tj",
                            "thermal",
                            "unknown",
                            "component is missing from network power_nodes",
                        )
                    )
                    continue
                if component.ref not in temps:
                    results.append(
                        check(
                            f"thermal.{component.ref}.tj",
                            "thermal",
                            "unknown",
                            "component is mapped to ambient rather than a powered network node",
                        )
                    )
                    continue
                temp = temps[component.ref]
                limit = component.tj_max_c - component.derating_margin_c
                results.append(
                    check(
                        f"thermal.{component.ref}.tj",
                        "thermal",
                        "pass" if temp <= limit else "fail",
                        f"network junction temperature {temp:.9g} °C",
                        measured=temp,
                        limit=f"≤ {limit:.9g} °C",
                    )
                )
            for ref, _node in network.power_nodes.items():
                if ref not in components:
                    results.append(
                        check(
                            f"thermal.{ref}.tj",
                            "thermal",
                            "unknown",
                            "network power node has no component temperature limit",
                        )
                    )
        except (ArithmeticError, KeyError, ValueError) as exc:
            results.append(check("thermal.network", "thermal", "unknown", str(exc)))
    return results or [check("thermal.components", "thermal", "unknown", "no components declared")]


def _tolerance(nominal: float, tol_pct: float | None, tol_abs: float | None) -> float:
    if tol_abs is not None:
        return tol_abs
    if tol_pct is None:
        raise ValueError("parameter tolerance is missing")
    return abs(nominal) * tol_pct / 100


def run_wca(section: WcaSection) -> list[GateCheck]:
    results: list[GateCheck] = []
    parameters = section.parameters
    for output in section.outputs:
        for method in section.methods:
            gate_id = f"wca.{method}.{output.name}"
            if output.expression is None:
                continue
            deltas = [
                _tolerance(parameter.nominal, parameter.tol_pct, parameter.tol_abs)
                + abs(parameter.nominal * parameter.temp_coeff_ppm / 1e6) * parameter.temp_range_c
                if parameter.temp_range_c is not None and parameter.temp_coeff_ppm is not None
                else _tolerance(parameter.nominal, parameter.tol_pct, parameter.tol_abs)
                for parameter in parameters
            ]
            try:
                nominal = {parameter.name: parameter.nominal for parameter in parameters}
                if method == "EVA":
                    count = 2 ** len(parameters)
                    if count > section.max_vertices:
                        results.append(
                            check(
                                gate_id, "wca", "unknown", f"{count} vertices exceed max_vertices"
                            )
                        )
                        continue
                    values = [
                        expr.evaluate(
                            output.expression,
                            {
                                parameter.name: parameter.nominal + sign * delta
                                for parameter, delta, sign in zip(
                                    parameters,
                                    deltas,
                                    signs,
                                    strict=True,
                                )
                            },
                        )
                        for signs in itertools.product((-1, 1), repeat=len(parameters))
                    ]
                    low, high = min(values), max(values)
                elif method == "RSS":
                    variance = 0.0
                    for parameter, delta in zip(parameters, deltas, strict=True):
                        step = max(abs(parameter.nominal) * 1e-6, 1e-9)
                        plus = dict(nominal)
                        minus = dict(nominal)
                        plus[parameter.name] += step
                        minus[parameter.name] -= step
                        sensitivity = (
                            expr.evaluate(output.expression, plus)
                            - expr.evaluate(output.expression, minus)
                        ) / (2 * step)
                        variance += (sensitivity * delta) ** 2
                    spread = math.sqrt(variance)
                    center = expr.evaluate(output.expression, nominal)
                    low, high = center - spread, center + spread
                else:
                    rng = random.Random(section.seed)
                    values: list[float] = []
                    for _ in range(section.mc_samples):
                        sample: dict[str, float] = {}
                        for parameter, delta in zip(parameters, deltas, strict=True):
                            sample[parameter.name] = (
                                rng.gauss(parameter.nominal, delta / 3)
                                if parameter.distribution == "normal"
                                else rng.uniform(
                                    parameter.nominal - delta, parameter.nominal + delta
                                )
                            )
                        values.append(expr.evaluate(output.expression, sample))
                    low, high = min(values), max(values)
                passed = (output.min is None or low >= output.min) and (
                    output.max is None or high <= output.max
                )
                verdict = (
                    "unknown"
                    if output.min is None and output.max is None
                    else "pass"
                    if passed
                    else "fail"
                )
                results.append(
                    check(
                        gate_id,
                        "wca",
                        verdict,
                        f"output range [{low:.9g}, {high:.9g}]",
                        measured=low,
                        limit=(f"min {output.min}; max {output.max}; measured_max {high:.9g}"),
                    )
                )
            except (ArithmeticError, ValueError) as exc:
                results.append(check(gate_id, "wca", "unknown", f"expression failed: {exc}"))
    return results


def run_emc(section: EmcSection) -> list[GateCheck]:
    results: list[GateCheck] = []
    signal_by_net = {signal.net: signal for signal in section.signals}
    device_by_net = {net: device for device in section.protected_devices for net in device.nets}
    protection_by_net: dict[str, list[EmcProtection]] = {}
    for protection in section.protections:
        for net in protection.nets:
            protection_by_net.setdefault(net, []).append(protection)
    for interface in section.interfaces:
        if not interface.external:
            continue
        required_rating = (
            (2, 4, 6, 8)[interface.esd_level - 1] if interface.esd_level is not None else None
        )
        for net in interface.nets:
            gate_id = f"emc.protection.{interface.connector_ref}.{net}"
            signal = signal_by_net.get(net)
            protections = protection_by_net.get(net, [])
            if not protections:
                results.append(check(gate_id, "emc", "fail", "external net has no ESD protection"))
                continue
            if signal is None or signal.v_max is None:
                results.append(check(gate_id, "emc", "unknown", "net maximum voltage is missing"))
                continue
            device = device_by_net.get(net)
            candidates = [
                (
                    protection,
                    (
                        protection.vrwm_v >= signal.v_max,
                        None
                        if required_rating is None
                        else protection.esd_rating_contact_kv >= required_rating,
                        protection.distance_to_connector_mm <= section.max_tvs_distance_mm,
                        None if device is None else protection.vclamp_v <= device.abs_max_v,
                    ),
                )
                for protection in protections
            ]
            passing = next(
                (
                    protection
                    for protection, rules in candidates
                    if all(rule is True for rule in rules)
                ),
                None,
            )
            unknown = any(rule is None for _, rules in candidates for rule in rules)
            results.append(
                check(
                    gate_id,
                    "emc",
                    "pass" if passing else "unknown" if unknown else "fail",
                    (
                        f"protection {passing.ref} meets all net limits"
                        if passing
                        else "ESD rating or protected-device limit is missing"
                        if unknown
                        else "no protection device meets all net limits"
                    ),
                )
            )
    for signal in section.signals:
        if signal.high_speed and signal.reference_plane_continuous is None:
            results.append(
                check(
                    f"emc.reference_plane.{signal.net}",
                    "emc",
                    "unknown",
                    "high-speed reference-plane continuity is undeclared",
                )
            )
        elif signal.high_speed and not signal.reference_plane_continuous:
            results.append(
                check(
                    f"emc.reference_plane.{signal.net}",
                    "emc",
                    "fail",
                    "high-speed signal lacks a continuous reference plane",
                )
            )
        if signal.length_mm is None or signal.rise_time_ns is None or signal.er_eff is None:
            results.append(
                check(
                    f"emc.critical_length.{signal.net}",
                    "emc",
                    "unknown",
                    "signal timing data missing",
                )
            )
        else:
            critical_mm = (
                signal.rise_time_ns * 1e-9 * 299_792_458 / math.sqrt(signal.er_eff) / 6 * 1000
            )
            passed = signal.length_mm <= critical_mm or signal.terminated
            results.append(
                check(
                    f"emc.critical_length.{signal.net}",
                    "emc",
                    "pass" if passed else "fail",
                    f"critical length {critical_mm:.9g} mm",
                    measured=signal.length_mm,
                    limit=f"≤ {critical_mm:.9g} mm or terminated",
                )
            )
    for item in section.decoupling:
        for pin in item.power_pins:
            gate_id = f"emc.decoupling.{item.ic_ref}.{pin}"
            if len(item.capacitors) < section.min_caps_per_pin:
                results.append(check(gate_id, "emc", "fail", "insufficient decoupling capacitors"))
            elif any(cap.distance_mm > section.max_decap_distance_mm for cap in item.capacitors):
                results.append(
                    check(gate_id, "emc", "fail", "decoupling capacitor exceeds distance limit")
                )
            else:
                results.append(
                    check(gate_id, "emc", "pass", "decoupling count and distance meet limits")
                )
    return results or [
        check("emc.inputs", "emc", "unknown", "no EMC predicates could be evaluated")
    ]


def run_dft(section: DftSection) -> list[GateCheck]:
    results: list[GateCheck] = []
    points_by_net: dict[str, list[TestPoint]] = {}
    for point in section.test_points:
        points_by_net.setdefault(point.net, []).append(point)
    required = set(section.nets)
    if section.required == "power_and_critical":
        required = set(section.nets) | set(section.critical_nets)
    elif section.required == "listed":
        required = set(section.critical_nets or section.nets)
    covered = required & points_by_net.keys()
    coverage = len(covered) / len(required) if required else 0.0
    results.append(
        check(
            "dft.coverage",
            "dft",
            ("unknown" if not required else "pass" if coverage >= section.min_coverage else "fail"),
            f"{len(covered)} of {len(required)} required nets have test points",
            measured=coverage,
            limit=f"≥ {section.min_coverage:.9g}",
        )
    )
    undersized = [
        point.ref
        for point in section.test_points
        if point.pad_diameter_mm < section.min_pad_diameter_mm
    ]
    results.append(
        check(
            "dft.pad_size",
            "dft",
            "unknown" if not section.test_points else "fail" if undersized else "pass",
            f"undersized pads: {', '.join(undersized) or 'none'}",
        )
    )
    close_pairs: list[str] = []
    for first, second in itertools.combinations(section.test_points, 2):
        if (
            first.side == second.side
            and math.hypot(first.x_mm - second.x_mm, first.y_mm - second.y_mm)
            < section.min_pitch_mm
        ):
            close_pairs.append(f"{first.ref}/{second.ref}")
    results.append(
        check(
            "dft.pitch",
            "dft",
            "unknown" if len(section.test_points) < 2 else "fail" if close_pairs else "pass",
            f"pairs below minimum pitch: {', '.join(close_pairs) or 'none'}",
        )
    )
    if section.require_debug_header:
        valid_header = section.debug_header is not None and section.debug_header.kind != "none"
        results.append(
            check(
                "dft.debug_header",
                "dft",
                "pass" if valid_header else "fail",
                "debug header declared" if valid_header else "required debug header is missing",
            )
        )
    if section.bga_refs:
        results.append(
            check(
                "dft.boundary_scan",
                "dft",
                "pass" if section.boundary_scan_chain else "fail",
                "boundary-scan chain declared"
                if section.boundary_scan_chain
                else "BGA devices need a boundary-scan chain",
            )
        )
    return results


def run_fem_analytic(section: FemSection) -> list[GateCheck]:
    geometry = section.geometry
    force = section.load.force_n
    length_m = geometry.length_mm / 1000
    width_m = geometry.width_mm / 1000
    height_m = geometry.height_mm / 1000
    stress_mpa = 6 * force * length_m / (width_m * height_m**2) / 1e6
    sf = section.material.yield_mpa / stress_mpa
    return [
        check(
            "fem.analytic.safety_factor",
            "fem",
            "pass" if sf >= section.limits.min_safety_factor else "fail",
            f"analytic beam safety factor {sf:.9g}",
            measured=sf,
            limit=f"≥ {section.limits.min_safety_factor:.9g}",
        ),
    ]


def run_bounds(
    nominal: float,
    tolerance: float,
    evaluator: Callable[[float], float],
) -> tuple[float, float]:
    low, high = evaluator(nominal - tolerance), evaluator(nominal + tolerance)
    return min(low, high), max(low, high)


def microstrip_impedance(
    width_mm: float, height_mm: float, thickness_um: float, er: float
) -> float:
    width = width_mm / height_mm
    thickness = thickness_um / 1000 / height_mm
    effective_width = width + thickness / math.pi * math.log(
        1 + 4 * math.e / (thickness * (1 / math.tanh(math.sqrt(6.517 * width))) ** 2)
    )
    effective_er = (er + 1) / 2 + (er - 1) / 2 / math.sqrt(1 + 12 / effective_width)
    if effective_width <= 1:
        impedance = (
            60 / math.sqrt(effective_er) * math.log(8 / effective_width + effective_width / 4)
        )
    else:
        impedance = (
            120
            * math.pi
            / (
                math.sqrt(effective_er)
                * (effective_width + 1.393 + 0.667 * math.log(effective_width + 1.444))
            )
        )
    return impedance
