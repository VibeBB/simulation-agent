"""Validated simulation brief models."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)


class ImportRef(Model):
    path: str = Field(min_length=1)
    system: Literal["circuit", "mech", "wire", "bard"]


class SpiceElement(Model):
    ref: str = Field(min_length=1)
    kind: Literal["R", "C", "L", "V", "I", "D", "X"]
    nodes: list[str] = Field(min_length=2)
    value: str = Field(min_length=1)
    model: str | None = None

    @model_validator(mode="after")
    def validate_lines(self) -> SpiceElement:
        fields = (self.ref, *self.nodes, self.value)
        if self.model is not None:
            fields += (self.model,)
        if any("\n" in value or "\r" in value for value in fields):
            raise ValueError("SPICE element fields must be single-line")
        return self


class Measure(Model):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    statement: str = Field(min_length=1)
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def validate_limits(self) -> Measure:
        if "\n" in self.statement or "\r" in self.statement:
            raise ValueError("SPICE measure statements must be single-line")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("measure minimum cannot exceed maximum")
        if not self.statement.lstrip().lower().startswith((".meas ", ".measure ")):
            raise ValueError("statement must be a full .meas line")
        if not re.search(rf"\b{re.escape(self.name)}\b", self.statement, re.IGNORECASE):
            raise ValueError("statement must name the declared measure")
        return self


class SpiceDeck(Model):
    netlist_path: str | None = None
    elements: list[SpiceElement] | None = None
    models: list[str] = Field(default_factory=list)
    analyses: list[str] = Field(min_length=1)
    measures: list[Measure] = Field(default_factory=lambda: list[Measure]())
    timeout_s: float = Field(default=120, gt=0)

    @model_validator(mode="after")
    def validate_deck(self) -> SpiceDeck:
        if (self.netlist_path is None) == (self.elements is None):
            raise ValueError("exactly one of netlist_path or elements is required")
        if len({measure.name.lower() for measure in self.measures}) != len(self.measures):
            raise ValueError("SPICE measure names must be unique")
        if any(
            "\n" in statement
            or "\r" in statement
            or not re.match(r"^\s*\.(?:include|model)\s+", statement, re.IGNORECASE)
            for statement in self.models
        ):
            raise ValueError("SPICE models must be single-line .model or .include statements")
        if any(
            "\n" in statement
            or "\r" in statement
            or not re.match(r"^\s*\.(?:ac|dc|noise|op|pz|tf|tran)\b", statement, re.IGNORECASE)
            for statement in self.analyses
        ):
            raise ValueError("SPICE analyses must be supported single-line directives")
        return self


class SpiceSection(Model):
    deck: SpiceDeck


class PdnLoad(Model):
    node: str = Field(min_length=1)
    current_a: float | str
    min_v: float | None = None
    return_node: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_current(self) -> PdnLoad:
        if isinstance(self.current_a, float) and self.current_a < 0:
            raise ValueError("current_a must be non-negative")
        if isinstance(self.current_a, str) and not self.current_a.startswith("import:"):
            raise ValueError("string current_a must use import:<net>")
        return self


class PdnBranch(Model):
    ref: str = Field(min_length=1)
    from_node: str = Field(min_length=1)
    to_node: str = Field(min_length=1)
    kind: Literal["trace", "plane", "via", "resistor", "wire"]
    length_mm: float | None = Field(default=None, gt=0)
    length_m: float | None = Field(default=None, gt=0)
    width_mm: float | None = Field(default=None, gt=0)
    copper_oz: float | None = Field(default=None, gt=0)
    thickness_um: float | None = Field(default=None, gt=0)
    layer: Literal["external", "internal"] = "external"
    allowed_rise_c: float = Field(default=10, gt=0)
    count: int | None = Field(default=None, ge=1)
    drill_mm: float | None = Field(default=None, gt=0)
    plating_um: float = Field(default=25, gt=0)
    resistance_ohm_per_km: float | None = Field(default=None, gt=0)
    resistance_ohm: float | None = Field(default=None, gt=0)
    ampacity_a: float | None = Field(default=None, gt=0)
    via_max_a: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_dimensions(self) -> PdnBranch:
        if self.kind in ("trace", "plane") and (self.length_mm is None or self.width_mm is None):
            raise ValueError(f"{self.kind} branch needs length_mm and width_mm")
        if self.kind in ("trace", "plane") and (
            self.copper_oz is None and self.thickness_um is None
        ):
            raise ValueError(f"{self.kind} branch needs copper_oz or thickness_um")
        if self.kind == "via" and (
            self.length_mm is None or self.count is None or self.drill_mm is None
        ):
            raise ValueError("via branch needs length_mm, count, and drill_mm")
        if self.kind == "resistor" and self.resistance_ohm is None:
            raise ValueError("resistor branch needs resistance_ohm")
        imported_wire = self.kind == "wire" and self.ref.startswith("import:")
        if (
            self.kind == "wire"
            and not imported_wire
            and (self.length_m is None or self.resistance_ohm_per_km is None)
        ):
            raise ValueError("wire branch needs length_m and resistance_ohm_per_km")
        if imported_wire and (self.length_m is not None or self.resistance_ohm_per_km is not None):
            raise ValueError("imported wire branch dimensions are resolved from its contract")
        return self


class PdnRail(Model):
    name: str = Field(min_length=1)
    source_v: float = Field(gt=0)
    max_drop_pct: float | None = Field(default=None, ge=0)
    max_drop_v: float | None = Field(default=None, ge=0)
    temperature_c: float = 25
    source_node: str = Field(min_length=1)
    return_source_node: str | None = Field(default=None, min_length=1)
    nodes: list[str] = Field(min_length=2)
    branches: list[PdnBranch] = Field(min_length=1)
    loads: list[PdnLoad] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_limits_and_refs(self) -> PdnRail:
        if self.max_drop_pct is None and self.max_drop_v is None:
            raise ValueError("a PDN rail needs max_drop_pct or max_drop_v")
        nodes = set(self.nodes)
        if self.source_node not in nodes:
            raise ValueError("source_node must be declared in nodes")
        if self.return_source_node is not None and (
            self.return_source_node not in nodes or self.return_source_node == self.source_node
        ):
            raise ValueError("return_source_node must be a distinct declared node")
        if any(
            branch.from_node not in nodes or branch.to_node not in nodes for branch in self.branches
        ):
            raise ValueError("branch endpoints must be declared in nodes")
        if any(load.node not in nodes for load in self.loads):
            raise ValueError("load nodes must be declared in nodes")
        if any(load.node in {self.source_node, self.return_source_node} for load in self.loads):
            raise ValueError("load node must not be a fixed source node")
        if self.return_source_node is not None and any(
            load.return_node is None
            or load.return_node not in nodes
            or load.return_node == self.source_node
            for load in self.loads
        ):
            raise ValueError("loads need a declared return_node when return_source_node is set")
        if self.return_source_node is None and any(
            load.return_node is not None for load in self.loads
        ):
            raise ValueError("load return_node requires return_source_node")
        if any(
            load.return_node is not None
            and (load.return_node not in nodes or load.return_node == self.source_node)
            for load in self.loads
        ):
            raise ValueError("load return_node must be a distinct declared node")
        if len(set(self.nodes)) != len(self.nodes):
            raise ValueError("nodes must be unique")
        if any(branch.from_node == branch.to_node for branch in self.branches):
            raise ValueError("branch endpoints must be distinct")
        if len({branch.ref for branch in self.branches}) != len(self.branches):
            raise ValueError("branch refs must be unique")
        return self


class PdnSection(Model):
    rails: list[PdnRail] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_names(self) -> PdnSection:
        if len({rail.name for rail in self.rails}) != len(self.rails):
            raise ValueError("rail names must be unique")
        return self


class ThermalPath(Model):
    theta_ja_c_per_w: float | None = Field(default=None, ge=0)
    theta_jc: float | None = Field(default=None, ge=0)
    theta_cs: float | None = Field(default=None, ge=0)
    theta_sa: float | None = Field(default=None, ge=0)


class ThermalComponent(Model):
    ref: str = Field(min_length=1)
    power_w: float = Field(ge=0)
    tj_max_c: float
    derating_margin_c: float = Field(default=0, ge=0)
    path: ThermalPath | None = None


class ThermalResistance(Model):
    a: str = Field(min_length=1)
    b: str = Field(min_length=1)
    c_per_w: float = Field(gt=0)


class ThermalNetwork(Model):
    nodes: list[str] = Field(min_length=2)
    resistances: list[ThermalResistance] = Field(min_length=1)
    power_nodes: dict[str, float]
    ambient_node: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_refs(self) -> ThermalNetwork:
        nodes = set(self.nodes)
        if self.ambient_node not in nodes:
            raise ValueError("ambient_node must be declared in nodes")
        if any(
            item.a not in nodes or item.b not in nodes or item.a == item.b
            for item in self.resistances
        ):
            raise ValueError("thermal resistance endpoints must be distinct declared nodes")
        if any(node not in nodes for node in self.power_nodes):
            raise ValueError("power_nodes must reference declared nodes")
        return self


class ThermalSection(Model):
    ambient_c: float
    components: list[ThermalComponent] = Field(default_factory=lambda: list[ThermalComponent]())
    network: ThermalNetwork | None = None

    @model_validator(mode="after")
    def validate_components(self) -> ThermalSection:
        if len({component.ref for component in self.components}) != len(self.components):
            raise ValueError("thermal component refs must be unique")
        if self.network is not None and len(set(self.network.nodes)) != len(self.network.nodes):
            raise ValueError("thermal network nodes must be unique")
        if self.network is not None and len(
            {(item.a, item.b) for item in self.network.resistances}
        ) != len(self.network.resistances):
            raise ValueError("thermal network resistance pairs must be unique")
        return self


class WcaParameter(Model):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    nominal: float
    tol_pct: float | None = Field(default=None, ge=0)
    tol_abs: float | None = Field(default=None, ge=0)
    distribution: Literal["uniform", "normal"] = "uniform"
    temp_coeff_ppm: float | None = None
    temp_range_c: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_tolerance(self) -> WcaParameter:
        if self.tol_pct is None and self.tol_abs is None:
            raise ValueError("parameter needs tol_pct or tol_abs")
        if self.tol_pct is not None and self.tol_abs is not None:
            raise ValueError("parameter cannot declare both tol_pct and tol_abs")
        if (self.temp_coeff_ppm is None) != (self.temp_range_c is None):
            raise ValueError("temp_coeff_ppm and temp_range_c must be specified together")
        return self


class WcaOutput(Model):
    name: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    expression: str | None = None
    spice_measure: str | None = None
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def require_source(self) -> WcaOutput:
        if (self.expression is None) == (self.spice_measure is None):
            raise ValueError("exactly one of expression or spice_measure is required")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("WCA minimum cannot exceed maximum")
        return self


class WcaSection(Model):
    parameters: list[WcaParameter] = Field(min_length=1)
    outputs: list[WcaOutput] = Field(min_length=1)
    methods: list[Literal["EVA", "RSS", "MC"]] = Field(min_length=1)
    mc_samples: int = Field(default=2000, ge=1)
    seed: int = 1
    max_vertices: int = Field(default=4096, ge=1)
    spice_mc_samples: int = Field(default=64, ge=1)

    @model_validator(mode="after")
    def validate_names(self) -> WcaSection:
        if len({parameter.name for parameter in self.parameters}) != len(self.parameters):
            raise ValueError("parameter names must be unique")
        if len({output.name for output in self.outputs}) != len(self.outputs):
            raise ValueError("output names must be unique")
        if len(set(self.methods)) != len(self.methods):
            raise ValueError("methods must be unique")
        return self


class EmcInterface(Model):
    connector_ref: str = Field(min_length=1)
    nets: list[str] = Field(min_length=1)
    esd_level: int | None = Field(default=None, ge=1, le=4)
    external: bool


class EmcProtection(Model):
    ref: str = Field(min_length=1)
    nets: list[str] = Field(min_length=1)
    vrwm_v: float = Field(ge=0)
    vclamp_v: float = Field(ge=0)
    esd_rating_contact_kv: float = Field(ge=0)
    distance_to_connector_mm: float = Field(ge=0)


class EmcDevice(Model):
    ref: str = Field(min_length=1)
    nets: list[str] = Field(min_length=1)
    abs_max_v: float = Field(ge=0)


class EmcSignal(Model):
    net: str = Field(min_length=1)
    v_max: float | None = Field(default=None, ge=0)
    rise_time_ns: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, ge=0)
    er_eff: float | None = Field(default=4.0, gt=0)
    terminated: bool = False
    reference_plane_continuous: bool | None = None
    high_speed: bool = False


class Decap(Model):
    ref: str = Field(min_length=1)
    distance_mm: float = Field(ge=0)


class Decoupling(Model):
    ic_ref: str = Field(min_length=1)
    power_pins: list[str] = Field(min_length=1)
    capacitors: list[Decap] = Field(default_factory=lambda: list[Decap]())


class EmcSection(Model):
    interfaces: list[EmcInterface] = Field(default_factory=lambda: list[EmcInterface]())
    protections: list[EmcProtection] = Field(default_factory=lambda: list[EmcProtection]())
    protected_devices: list[EmcDevice] = Field(default_factory=lambda: list[EmcDevice]())
    signals: list[EmcSignal] = Field(default_factory=lambda: list[EmcSignal]())
    decoupling: list[Decoupling] = Field(default_factory=lambda: list[Decoupling]())
    max_tvs_distance_mm: float = Field(default=10, ge=0)
    max_decap_distance_mm: float = Field(default=5, ge=0)
    min_caps_per_pin: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_refs(self) -> EmcSection:
        if len({item.connector_ref for item in self.interfaces}) != len(self.interfaces):
            raise ValueError("EMC interface connector refs must be unique")
        if len({item.net for item in self.signals}) != len(self.signals):
            raise ValueError("EMC signal nets must be unique")
        for refs, label in (
            ([item.ref for item in self.protections], "protection"),
            ([item.ref for item in self.protected_devices], "protected device"),
            ([item.ic_ref for item in self.decoupling], "decoupling IC"),
        ):
            if len(set(refs)) != len(refs):
                raise ValueError(f"EMC {label} refs must be unique")
        if any(len(set(item.nets)) != len(item.nets) for item in self.interfaces):
            raise ValueError("EMC interface nets must be unique")
        if any(len(set(item.nets)) != len(item.nets) for item in self.protections):
            raise ValueError("EMC protection nets must be unique")
        if any(
            len({capacitor.ref for capacitor in item.capacitors}) != len(item.capacitors)
            for item in self.decoupling
        ):
            raise ValueError("decoupling capacitor refs must be unique per IC")
        return self


class TestPoint(Model):
    __test__: ClassVar[bool] = False
    ref: str = Field(min_length=1)
    net: str = Field(min_length=1)
    pad_diameter_mm: float = Field(gt=0)
    x_mm: float
    y_mm: float
    side: Literal["top", "bottom"]


class DebugHeader(Model):
    kind: Literal["swd", "jtag", "uart", "none"]
    ref: str = Field(min_length=1)


class DftSection(Model):
    nets: list[str] = Field(default_factory=list)
    test_points: list[TestPoint] = Field(default_factory=lambda: list[TestPoint]())
    required: Literal["all", "power_and_critical", "listed"]
    critical_nets: list[str] = Field(default_factory=list)
    min_coverage: float = Field(default=1.0, ge=0, le=1)
    min_pad_diameter_mm: float = Field(default=0.9, gt=0)
    min_pitch_mm: float = Field(default=2.54, ge=0)
    debug_header: DebugHeader | None = None
    require_debug_header: bool = True
    bga_refs: list[str] = Field(default_factory=list)
    boundary_scan_chain: bool = False

    @model_validator(mode="after")
    def validate_names(self) -> DftSection:
        if len(set(self.nets)) != len(self.nets):
            raise ValueError("DFT nets must be unique")
        if len(set(self.critical_nets)) != len(self.critical_nets):
            raise ValueError("DFT critical_nets must be unique")
        if len({point.ref for point in self.test_points}) != len(self.test_points):
            raise ValueError("test point refs must be unique")
        return self


class FemGeometry(Model):
    kind: Literal["cantilever_box"]
    length_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)


class FemMaterial(Model):
    name: str = Field(min_length=1)
    youngs_mpa: float = Field(gt=0)
    poisson: float = Field(gt=-1, lt=0.5)
    yield_mpa: float = Field(gt=0)
    density_kg_m3: float | None = Field(default=None, gt=0)


class FemLoad(Model):
    kind: Literal["tip_force"]
    force_n: float = Field(gt=0)
    direction: Literal["-z"]


class FemMesh(Model):
    nx: int = Field(ge=1)
    ny: int = Field(ge=1)
    nz: int = Field(ge=1)
    element: Literal["C3D20R", "C3D8I"]


class FemLimits(Model):
    min_safety_factor: float = Field(default=2, gt=0)
    max_deflection_mm: float | None = Field(default=None, gt=0)


class FemSection(Model):
    geometry: FemGeometry
    material: FemMaterial
    load: FemLoad
    mesh: FemMesh
    limits: FemLimits = Field(default_factory=FemLimits)
    cross_check_tolerance: float = Field(default=0.15, ge=0)
    timeout_s: float = Field(default=300, gt=0)


class RfBand(Model):
    name: str = Field(min_length=1)
    f_min_hz: float = Field(gt=0)
    f_max_hz: float = Field(gt=0)
    s11_max_db: float | None = None
    s21_min_db: float | None = None
    vswr_max: float | None = Field(default=None, gt=1)

    @model_validator(mode="after")
    def validate_band(self) -> RfBand:
        if self.f_max_hz <= self.f_min_hz:
            raise ValueError("f_max_hz must exceed f_min_hz")
        return self


class Microstrip(Model):
    name: str = Field(min_length=1)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    thickness_um: float = Field(default=35, gt=0)
    er: float = Field(gt=1)
    target_ohm: float = Field(gt=0)
    tol_pct: float = Field(default=10, ge=0)


class RfSim(Model):
    model_path: str = Field(min_length=1)
    runner_path: str | None = None
    timeout_s: float = Field(default=3600, gt=0)


class RfSection(Model):
    touchstone_path: str | None = None
    rfsim: RfSim | None = None
    microstrip: list[Microstrip] = Field(default_factory=lambda: list[Microstrip]())
    bands: list[RfBand] = Field(default_factory=lambda: list[RfBand]())

    @model_validator(mode="after")
    def require_input(self) -> RfSection:
        if self.touchstone_path is None and self.rfsim is None and not self.microstrip:
            raise ValueError("RF section needs touchstone_path, rfsim, or microstrip")
        if self.touchstone_path is not None and self.rfsim is not None:
            raise ValueError("RF section must use either touchstone_path or rfsim")
        if len({band.name for band in self.bands}) != len(self.bands):
            raise ValueError("RF band names must be unique")
        return self


class RuggedPlate(Model):
    width_mm: float = Field(gt=0)
    depth_mm: float = Field(gt=0)
    thickness_mm: float = Field(gt=0)
    youngs_mpa: float = Field(gt=0)
    poisson: float = Field(gt=-1, lt=0.5)
    density_kg_m3: float = Field(gt=0)
    component_mass_g: float = Field(ge=0)


class RuggedPart(Model):
    ref: str = Field(min_length=1)
    x_mm: float
    y_mm: float
    length_mm: float = Field(gt=0)
    parallel_to: Literal["width", "depth"]
    steinberg_c: float = Field(gt=0)


class RuggedVibration(Model):
    psd_g2_hz: float = Field(gt=0)
    q: float | None = Field(default=None, gt=0)
    min_fn_hz: float | None = Field(default=None, gt=0)
    parts: list[RuggedPart] = Field(min_length=1)


class RuggedDrop(Model):
    height_mm: float = Field(gt=0)
    pulse_ms: float = Field(gt=0)
    restitution: float = Field(ge=0, le=1)
    max_shock_g: float = Field(gt=0)


class RuggedIngress(Model):
    code: str = Field(pattern=r"^IP[0-6X][0-9X]$")
    openings_min_mm: list[float] = Field(default_factory=lambda: list[float]())
    sealed: bool

    @model_validator(mode="after")
    def validate_openings(self) -> RuggedIngress:
        if any(not value > 0 for value in self.openings_min_mm):
            raise ValueError("opening dimensions must be positive")
        return self


class RuggednessSection(Model):
    plate: RuggedPlate | None = None
    vibration: RuggedVibration | None = None
    drop: RuggedDrop | None = None
    ingress: RuggedIngress | None = None

    @model_validator(mode="after")
    def validate_inputs(self) -> RuggednessSection:
        if self.vibration is None and self.drop is None and self.ingress is None:
            raise ValueError("ruggedness needs vibration, drop, or ingress")
        if self.vibration is not None and self.plate is None:
            raise ValueError("ruggedness vibration needs plate")
        if self.vibration is not None:
            refs = [part.ref for part in self.vibration.parts]
            if len(set(refs)) != len(refs):
                raise ValueError("ruggedness part refs must be unique")
        return self


class LifetimeStress(Model):
    temperature_c: float = Field(gt=-273.15)
    fraction: float = Field(gt=0, le=1)


class LifetimePart(Model):
    ref: str = Field(min_length=1)
    rated_life_h: float = Field(gt=0)
    rated_temp_c: float = Field(gt=-273.15)
    activation_energy_ev: float = Field(gt=0)
    profile: list[LifetimeStress] = Field(min_length=1)
    required_life_h: float = Field(gt=0)
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_profile(self) -> LifetimePart:
        if abs(sum(stress.fraction for stress in self.profile) - 1) > 1e-9:
            raise ValueError("lifetime profile fractions must sum to 1")
        return self


class LifetimeSection(Model):
    model: Literal["arrhenius"] = "arrhenius"
    parts: list[LifetimePart] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_refs(self) -> LifetimeSection:
        refs = [part.ref for part in self.parts]
        if len(set(refs)) != len(refs):
            raise ValueError("lifetime part refs must be unique")
        return self


class SimulationBrief(Model):
    schema_version: Literal[1]
    name: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    description: str = ""
    imports: list[ImportRef] = Field(default_factory=lambda: list[ImportRef]())
    spice: SpiceSection | None = None
    pdn: PdnSection | None = None
    thermal: ThermalSection | None = None
    wca: WcaSection | None = None
    emc: EmcSection | None = None
    dft: DftSection | None = None
    fem: FemSection | None = None
    rf: RfSection | None = None
    ruggedness: RuggednessSection | None = None
    lifetime: LifetimeSection | None = None

    @model_validator(mode="after")
    def require_section(self) -> SimulationBrief:
        if not any(
            getattr(self, key) is not None
            for key in (
                "spice",
                "pdn",
                "thermal",
                "wca",
                "emc",
                "dft",
                "fem",
                "rf",
                "ruggedness",
                "lifetime",
            )
        ):
            raise ValueError("at least one analysis section is required")
        return self


def load_brief(path: Path) -> SimulationBrief:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load simulation brief {path}: {exc}") from exc
    return SimulationBrief.model_validate(value)


def schema() -> dict[str, object]:
    return SimulationBrief.model_json_schema()
