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
    LifetimePart,
    LifetimeSection,
    PdnBranch,
    PdnRail,
    RuggedDrop,
    RuggedIngress,
    RuggednessSection,
    RuggedPlate,
    RuggedVibration,
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


def thermal_guidance(
    ref: str,
    *,
    ambient_c: float,
    limit_c: float,
    power_w: float,
    self_c_per_w: float,
    other_rise_c: float,
) -> list[str]:
    """Inverse solutions of Tj = Ta + P·Z_self + other rise for a failing junction."""
    headroom = limit_c - ambient_c - other_rise_c
    lines = [
        f"sensitivity: dTj/dP({ref}) = {self_c_per_w:.6g} °C/W, "
        f"dTj/dθ = {power_w:.6g} W, dTj/dTa = 1",
        f"ambient_c ≤ {limit_c - (power_w * self_c_per_w + other_rise_c):.6g} °C "
        "at the current power and thermal path",
    ]
    if headroom <= 0:
        lines.append(
            f"{ref} exceeds {limit_c:.6g} °C even at zero own power "
            f"(ambient plus other sources give {ambient_c + other_rise_c:.6g} °C); "
            "lower ambient or the other sources, or raise tj_max_c/derating basis"
        )
        return lines
    if self_c_per_w > 0:
        lines.append(f"power_w({ref}) ≤ {headroom / self_c_per_w:.6g} W at the current θ")
    if power_w > 0:
        lines.append(f"θ({ref}) ≤ {headroom / power_w:.6g} °C/W at the current power")
    return lines


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
                    margin=limit - temp,
                    guidance=[]
                    if temp <= limit
                    else thermal_guidance(
                        component.ref,
                        ambient_c=section.ambient_c,
                        limit_c=limit,
                        power_w=component.power_w,
                        self_c_per_w=theta,
                        other_rise_c=0.0,
                    ),
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
                guidance: list[str] = []
                if temp > limit:
                    unit = [0.0 for _ in unknown]
                    unit[indexes[component.ref]] = 1.0
                    self_c_per_w = linalg.solve(matrix, unit)[indexes[component.ref]]
                    power = network.power_nodes[component.ref]
                    guidance = thermal_guidance(
                        component.ref,
                        ambient_c=section.ambient_c,
                        limit_c=limit,
                        power_w=power,
                        self_c_per_w=self_c_per_w,
                        other_rise_c=temp - section.ambient_c - power * self_c_per_w,
                    )
                results.append(
                    check(
                        f"thermal.{component.ref}.tj",
                        "thermal",
                        "pass" if temp <= limit else "fail",
                        f"network junction temperature {temp:.9g} °C",
                        measured=temp,
                        limit=f"≤ {limit:.9g} °C",
                        margin=limit - temp,
                        guidance=guidance,
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
        has_timing_data = (
            signal.length_mm is not None or signal.rise_time_ns is not None or signal.high_speed
        )
        if not has_timing_data:
            continue
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


STANDARD_GRAVITY = 9.80665
MM_PER_INCH = 25.4
IP_FIRST_DIGIT_PROBE_MM = {"1": 50.0, "2": 12.5, "3": 2.5, "4": 1.0}


def plate_natural_frequency(plate: RuggedPlate) -> float:
    """First mode of a simply supported rectangular plate (Steinberg), Hz."""
    a = plate.width_mm / 1000
    b = plate.depth_mm / 1000
    h = plate.thickness_mm / 1000
    rigidity = plate.youngs_mpa * 1e6 * h**3 / (12 * (1 - plate.poisson**2))
    areal_mass = plate.density_kg_m3 * h + plate.component_mass_g / 1000 / (a * b)
    return math.pi / 2 * math.sqrt(rigidity / areal_mass) * (1 / a**2 + 1 / b**2)


def plate_fn_guidance(plate: RuggedPlate, fn: float, target_hz: float) -> list[str]:
    """Single-parameter changes that lift the plate first mode to ``target_hz``."""
    lines = [f"youngs_mpa ≥ {plate.youngs_mpa * (target_hz / fn) ** 2:.6g} (fn ∝ √E)"]
    a = plate.width_mm / 1000
    b = plate.depth_mm / 1000
    h = plate.thickness_mm / 1000
    rigidity = plate.youngs_mpa * 1e6 * h**3 / (12 * (1 - plate.poisson**2))
    areal_max = rigidity / (target_hz / (math.pi / 2 * (1 / a**2 + 1 / b**2))) ** 2
    mass_max_g = (areal_max - plate.density_kg_m3 * h) * a * b * 1000
    if mass_max_g >= 0:
        lines.append(f"component_mass_g ≤ {mass_max_g:.6g}")
    else:
        lines.append("bare plate is below target even without components")
    low, high = plate.thickness_mm, plate.thickness_mm
    for _ in range(60):
        high *= 2
        if plate_natural_frequency(plate.model_copy(update={"thickness_mm": high})) >= target_hz:
            break
    else:
        return lines
    for _ in range(80):
        mid = (low + high) / 2
        if plate_natural_frequency(plate.model_copy(update={"thickness_mm": mid})) >= target_hz:
            high = mid
        else:
            low = mid
    lines.append(f"thickness_mm ≥ {high:.6g}")
    return lines


def _run_vibration(plate: RuggedPlate, vibration: RuggedVibration) -> list[GateCheck]:
    fn = plate_natural_frequency(plate)
    checks: list[GateCheck] = []
    if vibration.min_fn_hz is not None:
        checks.append(
            check(
                "ruggedness.vibration.fn",
                "ruggedness",
                "pass" if fn >= vibration.min_fn_hz else "fail",
                f"plate first mode {fn:.6g} Hz",
                measured=fn,
                limit=f"≥ {vibration.min_fn_hz:.6g} Hz",
                margin=fn - vibration.min_fn_hz,
                guidance=[]
                if fn >= vibration.min_fn_hz
                else plate_fn_guidance(plate, fn, vibration.min_fn_hz),
            )
        )
    q = vibration.q if vibration.q is not None else math.sqrt(fn)
    g_rms = math.sqrt(math.pi / 2 * fn * q * vibration.psd_g2_hz)
    z3_mm = 3 * g_rms * STANDARD_GRAVITY / (2 * math.pi * fn) ** 2 * 1000
    h_in = plate.thickness_mm / MM_PER_INCH
    for part in vibration.parts:
        edge_mm = plate.width_mm if part.parallel_to == "width" else plate.depth_mm
        r = abs(
            math.cos(math.pi * part.x_mm / plate.width_mm)
            * math.cos(math.pi * part.y_mm / plate.depth_mm)
        )
        inside = abs(part.x_mm) <= plate.width_mm / 2 and abs(part.y_mm) <= plate.depth_mm / 2
        if not inside:
            checks.append(
                check(
                    f"ruggedness.vibration.{part.ref}",
                    "ruggedness",
                    "unknown",
                    "part position lies outside the plate",
                )
            )
            continue
        if r < 1e-9:
            checks.append(
                check(
                    f"ruggedness.vibration.{part.ref}",
                    "ruggedness",
                    "pass",
                    "part sits on a supported edge (no relative displacement)",
                    measured=z3_mm,
                )
            )
            continue
        allowable_mm = (
            0.00022
            * (edge_mm / MM_PER_INCH)
            / (part.steinberg_c * h_in * r * math.sqrt(part.length_mm / MM_PER_INCH))
            * MM_PER_INCH
        )
        checks.append(
            check(
                f"ruggedness.vibration.{part.ref}",
                "ruggedness",
                "pass" if z3_mm <= allowable_mm else "fail",
                f"3-sigma board displacement {z3_mm:.6g} mm at fn {fn:.6g} Hz, "
                f"Q {q:.6g}, {g_rms:.6g} Grms; Steinberg allowable {allowable_mm:.6g} mm",
                measured=z3_mm,
                limit=f"≤ {allowable_mm:.6g} mm",
                margin=allowable_mm - z3_mm,
                guidance=[]
                if z3_mm <= allowable_mm
                else [
                    f"psd_g2_hz ≤ {vibration.psd_g2_hz * (allowable_mm / z3_mm) ** 2:.6g} "
                    "(displacement ∝ √PSD at fixed fn and Q)",
                    f"move {part.ref} toward a supported edge: mode-shape factor "
                    f"{r:.6g} → ≤ {r * allowable_mm / z3_mm:.6g} (allowable ∝ 1/r)",
                    "raise the plate first mode (displacement ∝ fn^-2 at fixed Grms)",
                ],
            )
        )
    return checks


def drop_peak_g(drop: RuggedDrop) -> float:
    """Peak acceleration of a half-sine pulse absorbing the drop velocity change, g."""
    velocity = math.sqrt(2 * STANDARD_GRAVITY * drop.height_mm / 1000)
    delta_v = (1 + drop.restitution) * velocity
    return math.pi * delta_v / (2 * drop.pulse_ms / 1000) / STANDARD_GRAVITY


def drop_guidance(drop: RuggedDrop, peak: float) -> list[str]:
    """Single-parameter changes that bring the half-sine peak to ``max_shock_g``."""
    ratio = drop.max_shock_g / peak
    lines = [
        f"pulse_ms ≥ {drop.pulse_ms / ratio:.6g} (cushioning; peak ∝ 1/pulse)",
        f"height_mm ≤ {drop.height_mm * ratio**2:.6g} (peak ∝ √height)",
    ]
    restitution = (1 + drop.restitution) * ratio - 1
    if restitution >= 0:
        lines.append(f"restitution ≤ {restitution:.6g} (peak ∝ 1 + e)")
    lines.append(f"or qualify parts to max_shock_g ≥ {peak:.6g}")
    return lines


def _run_drop(drop: RuggedDrop) -> list[GateCheck]:
    peak = drop_peak_g(drop)
    return [
        check(
            "ruggedness.drop.peak_g",
            "ruggedness",
            "pass" if peak <= drop.max_shock_g else "fail",
            f"half-sine peak {peak:.6g} g for a {drop.height_mm:.6g} mm drop "
            f"over {drop.pulse_ms:.6g} ms",
            measured=peak,
            limit=f"≤ {drop.max_shock_g:.6g} g",
            margin=drop.max_shock_g - peak,
            guidance=[] if peak <= drop.max_shock_g else drop_guidance(drop, peak),
        )
    ]


def _run_ingress(ingress: RuggedIngress) -> list[GateCheck]:
    solids, water = ingress.code[2], ingress.code[3]
    checks: list[GateCheck] = []
    if solids in IP_FIRST_DIGIT_PROBE_MM:
        probe = IP_FIRST_DIGIT_PROBE_MM[solids]
        worst = max(ingress.openings_min_mm, default=0.0)
        checks.append(
            check(
                "ruggedness.ingress.solids",
                "ruggedness",
                "pass" if worst < probe else "fail",
                f"largest opening {worst:.6g} mm against the IP{solids}X {probe:.6g} mm probe",
                measured=worst,
                limit=f"< {probe:.6g} mm",
                margin=probe - worst,
                guidance=[]
                if worst < probe
                else [
                    f"narrow every opening of {probe:.6g} mm or more below the probe "
                    f"(largest {worst:.6g} mm), or add a guard"
                ],
            )
        )
    elif solids in ("5", "6"):
        checks.append(
            check(
                "ruggedness.ingress.solids",
                "ruggedness",
                "unknown",
                f"IP{solids}X dust protection needs an IEC 60529 dust-chamber test",
            )
        )
    if water not in ("X", "0"):
        if ingress.openings_min_mm and not ingress.sealed:
            checks.append(
                check(
                    "ruggedness.ingress.water",
                    "ruggedness",
                    "fail",
                    f"IPX{water} with unsealed openings",
                )
            )
        else:
            checks.append(
                check(
                    "ruggedness.ingress.water",
                    "ruggedness",
                    "unknown",
                    f"IPX{water} water protection needs an IEC 60529 water test",
                )
            )
    return checks


def run_ruggedness(section: RuggednessSection) -> list[GateCheck]:
    checks: list[GateCheck] = []
    if section.vibration is not None and section.plate is not None:
        checks += _run_vibration(section.plate, section.vibration)
    if section.drop is not None:
        checks += _run_drop(section.drop)
    if section.ingress is not None:
        checks += _run_ingress(section.ingress)
    return checks


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


BOLTZMANN_EV_PER_K = 8.617333262e-5
KELVIN = 273.15


def arrhenius_life_h(part: LifetimePart, shift_c: float = 0.0) -> float:
    """Miner-summed Arrhenius life over the mission profile, hours."""
    t_ref = part.rated_temp_c + KELVIN
    damage = 0.0
    for stress in part.profile:
        t_use = stress.temperature_c + shift_c + KELVIN
        exponent = part.activation_energy_ev / BOLTZMANN_EV_PER_K * (1 / t_use - 1 / t_ref)
        damage += stress.fraction / (part.rated_life_h * math.exp(exponent))
    return 1 / damage


def lifetime_guidance(part: LifetimePart, life_h: float) -> list[str]:
    """Temperature drop and rated-life changes that reach ``required_life_h``."""
    hottest = max(stress.temperature_c for stress in part.profile) + KELVIN
    doubling_k = math.log(2) * BOLTZMANN_EV_PER_K * hottest**2 / part.activation_energy_ev
    lines = [
        f"sensitivity: life doubles per {doubling_k:.3g} K cooler near "
        f"{hottest - KELVIN:.6g} °C (Ea {part.activation_energy_ev:.6g} eV)",
        f"rated_life_h ≥ {part.rated_life_h * part.required_life_h / life_h:.6g} "
        f"at {part.rated_temp_c:.6g} °C (life ∝ rated life)",
    ]
    low, high = 0.0, 1.0
    floor = -(min(stress.temperature_c for stress in part.profile) + KELVIN) + 1e-6
    while arrhenius_life_h(part, -high) < part.required_life_h:
        high *= 2
        if -high <= floor:
            return lines
    for _ in range(80):
        mid = (low + high) / 2
        if arrhenius_life_h(part, -mid) >= part.required_life_h:
            high = mid
        else:
            low = mid
    lines.insert(1, f"lower every profile temperature by ≥ {high:.6g} °C")
    return lines


def run_lifetime(section: LifetimeSection) -> list[GateCheck]:
    checks: list[GateCheck] = []
    for part in section.parts:
        check_id = f"lifetime.{part.ref}.life_h"
        try:
            life = arrhenius_life_h(part)
        except (OverflowError, ZeroDivisionError):
            checks.append(check(check_id, "lifetime", "unknown", "Arrhenius factor out of range"))
            continue
        ok = life >= part.required_life_h
        detail = (
            f"Arrhenius life {life:.6g} h (rated {part.rated_life_h:.6g} h at "
            f"{part.rated_temp_c:.6g} °C, Ea {part.activation_energy_ev:.6g} eV, "
            f"{len(part.profile)} profile step(s); source: {part.source}); "
            f"margin {life - part.required_life_h:.6g} h"
        )
        if not ok:
            detail = f"{detail}; fix: {' | '.join(lifetime_guidance(part, life))}"
        checks.append(
            check(
                check_id,
                "lifetime",
                "pass" if ok else "fail",
                detail,
                measured=life,
                limit=f"≥ {part.required_life_h:.6g} h",
                evidence=[part.source],
            )
        )
    return checks
