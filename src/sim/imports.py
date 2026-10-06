"""Strict mirrors of sibling workspace contracts and import provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .workspace import reject_symlinks, workspace_path


def _object_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    mapping = cast(dict[object, object], value)
    result: dict[str, object] = {}
    for key, item in mapping.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)


class ContractElementSource(StrictModel):
    system: Literal["manual", "circuit", "mech", "csv", "kbl", "vec"]
    ref: str = Field(min_length=1)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ContractTemperaturePoint(StrictModel):
    temperature_c: float
    factor: float = Field(ge=0, le=1)


class ConnectorSource(StrictModel):
    ref: str = Field(min_length=1)
    family_hint: str | None = None
    housing: str | None = None
    rated_current_a: float = Field(default=3, gt=0)
    rated_voltage_v: float = Field(default=250, gt=0)
    cavities: list[str] = Field(min_length=1)


class NetSource(StrictModel):
    ref: str = Field(min_length=1)
    signal_class: Literal["power", "ground", "signal", "analog", "data", "highspeed", "shield"] = (
        "signal"
    )
    voltage_v: float = Field(ge=0)
    current_a: float = Field(ge=0)


class ConnectivitySource(StrictModel):
    schema_version: Literal[1] = 1
    system: Literal["circuit", "csv", "kbl", "vec"] = "circuit"
    connectors: list[ConnectorSource] = Field(default_factory=lambda: list[ConnectorSource]())
    nets: list[NetSource] = Field(default_factory=lambda: list[NetSource]())


class EnvelopeAnchor(StrictModel):
    name: str = Field(min_length=1)
    kind: Literal["clip", "grommet", "breakout", "other"] = "other"
    position_mm: tuple[float, float, float] | None = None


class EnvelopeSource(StrictModel):
    schema_version: Literal[1] = 1
    system: Literal["mech"] = "mech"
    anchors: list[EnvelopeAnchor] = Field(min_length=1)


class ContractWireType(StrictModel):
    id: str = Field(pattern=r"^WT[0-9]+$")
    name: str = Field(min_length=1)
    spec: str | None = None
    gauge_mm2: float = Field(gt=0)
    outer_diameter_mm: float = Field(gt=0)
    resistance_ohm_per_km: float = Field(gt=0)
    ampacity_a: float = Field(gt=0)
    reference_temp_c: float
    insulation_rating_v: float = Field(gt=0)
    insulation_temp_c: float
    min_bend_factor: float = Field(gt=0)
    temp_derating: list[ContractTemperaturePoint] = Field(
        default_factory=lambda: list[ContractTemperaturePoint]()
    )
    shield: Literal["none", "braid", "foil"] = "none"
    flex_class: Literal["static", "dynamic", "high_flex"] = "static"
    source: ContractElementSource | None = None

    @model_validator(mode="after")
    def validate_derating(self) -> ContractWireType:
        temperatures = [point.temperature_c for point in self.temp_derating]
        if temperatures != sorted(temperatures):
            raise ValueError("temp_derating must be sorted by temperature_c")
        return self


class ContractCavity(StrictModel):
    id: str = Field(min_length=1)
    accepts_mm2: tuple[float, float] | None = None
    terminal: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> ContractCavity:
        if self.accepts_mm2 is not None:
            minimum, maximum = self.accepts_mm2
            if minimum <= 0 or maximum < minimum:
                raise ValueError("accepts_mm2 must be (min, max) with 0 < min <= max")
        return self


class ContractConnector(StrictModel):
    id: str = Field(pattern=r"^C[0-9]+$")
    family: str = Field(min_length=1)
    housing: str | None = None
    mate: str | None = None
    rated_current_a: float = Field(gt=0)
    rated_voltage_v: float = Field(gt=0)
    mating_cycles: int = Field(default=30, ge=1)
    keying: str | None = None
    sealed: bool = False
    temp_rating_c: float | None = None
    cavity_count: int | None = Field(default=None, ge=1)
    cavities: list[ContractCavity] = Field(min_length=1)
    source: ContractElementSource | None = None

    @model_validator(mode="after")
    def validate_cavities(self) -> ContractConnector:
        if len({cavity.id for cavity in self.cavities}) != len(self.cavities):
            raise ValueError("cavity ids must be unique within a connector")
        if self.cavity_count is not None and len(self.cavities) > self.cavity_count:
            raise ValueError("cavity_count smaller than declared cavities")
        return self


class ContractNet(StrictModel):
    id: str = Field(pattern=r"^N[0-9]+$")
    signal_class: Literal["power", "ground", "signal", "analog", "data", "highspeed", "shield"]
    voltage_v: float = Field(ge=0)
    current_a: float = Field(ge=0)
    ref: str | None = None
    max_voltage_drop_v: float | None = Field(default=None, ge=0)
    shield_required: bool = False
    twisted_pair_with: str | None = Field(default=None, pattern=r"^N[0-9]+$")
    source: ContractElementSource | None = None


class Endpoint(StrictModel):
    connector: str | None = Field(default=None, pattern=r"^C[0-9]+$")
    cavity: str | None = Field(default=None, min_length=1)
    splice: str | None = Field(default=None, pattern=r"^SP[0-9]+$")

    @model_validator(mode="after")
    def validate_endpoint(self) -> Endpoint:
        if self.splice is not None:
            if self.connector is not None or self.cavity is not None:
                raise ValueError("splice endpoints cannot set connector or cavity")
        elif self.connector is None or self.cavity is None:
            raise ValueError("endpoints need connector+cavity or splice")
        return self


class ContractSplice(StrictModel):
    id: str = Field(pattern=r"^SP[0-9]+$")
    kind: Literal["crimp", "solder", "ultrasonic", "ferrule"] = "crimp"
    source: ContractElementSource | None = None


class ContractWire(StrictModel):
    id: str = Field(pattern=r"^W[0-9]+$")
    wire_type: str = Field(pattern=r"^WT[0-9]+$")
    net: str = Field(pattern=r"^N[0-9]+$")
    from_endpoint: Endpoint
    to_endpoint: Endpoint
    length_m: float = Field(gt=0)
    color: str | None = None
    strip_a_mm: float = Field(default=4, gt=0)
    strip_b_mm: float = Field(default=4, gt=0)
    terminal_a: str | None = None
    terminal_b: str | None = None
    route: str | None = Field(default=None, pattern=r"^RT[0-9]+$")


class ContractSegment(StrictModel):
    id: str = Field(pattern=r"^S[0-9]+$")
    length_m: float = Field(gt=0)
    min_bend_radius_mm: float | None = Field(default=None, gt=0)


class ContractRoute(StrictModel):
    id: str = Field(pattern=r"^RT[0-9]+$")
    segments: list[ContractSegment] = Field(min_length=1)
    protection: Literal["none", "tape", "tube", "conduit", "sleeve"] = "none"
    flex_required: bool = False
    anchors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_segments(self) -> ContractRoute:
        if len({segment.id for segment in self.segments}) != len(self.segments):
            raise ValueError("segment ids must be unique within a route")
        return self


class ContractSegregation(StrictModel):
    classes: tuple[
        Literal["power", "ground", "signal", "analog", "data", "highspeed", "shield"],
        Literal["power", "ground", "signal", "analog", "data", "highspeed", "shield"],
    ]
    rule: Literal["no_shared_route", "no_shared_connector"]


class ContractService(StrictModel):
    mating_cycles: int | None = Field(default=None, ge=1)
    flex_cycles: int | None = Field(default=None, ge=1)


class ContractImportedSource(StrictModel):
    id: str = Field(pattern=r"^I[0-9]+$")
    system: Literal["manual", "circuit", "mech", "csv", "kbl", "vec"]
    ref: str = Field(min_length=1)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    description: str = ""
    anchors: list[str] = Field(default_factory=list)


class WireContract(StrictModel):
    schema_version: Literal[1] = 1
    contract_id: str = Field(pattern=r"^WH-[0-9A-Za-z-]+$")
    name: str
    revision: str
    ipc_class: Literal[1, 2, 3] = 2
    ambient_temperature_c: float = 25
    connectors: list[ContractConnector] = Field(default_factory=lambda: list[ContractConnector]())
    wire_types: list[ContractWireType] = Field(default_factory=lambda: list[ContractWireType]())
    nets: list[ContractNet] = Field(default_factory=lambda: list[ContractNet]())
    wires: list[ContractWire] = Field(default_factory=lambda: list[ContractWire]())
    routes: list[ContractRoute] = Field(default_factory=lambda: list[ContractRoute]())
    splices: list[ContractSplice] = Field(default_factory=lambda: list[ContractSplice]())
    segregations: list[ContractSegregation] = Field(
        default_factory=lambda: list[ContractSegregation]()
    )
    service: ContractService | None = None
    simulation: dict[str, object] | None = None
    imported_sources: list[ContractImportedSource] = Field(
        default_factory=lambda: list[ContractImportedSource]()
    )
    drawing: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> WireContract:
        for collection, label in (
            (self.connectors, "connector"),
            (self.wire_types, "wire type"),
            (self.nets, "net"),
            (self.wires, "wire"),
            (self.routes, "route"),
            (self.splices, "splice"),
            (self.imported_sources, "imported source"),
        ):
            ids = [item.id for item in collection]
            if len(set(ids)) != len(ids):
                raise ValueError(f"{label} ids must be unique")
        connector_ids = {item.id for item in self.connectors}
        cavities = {
            (connector.id, cavity.id)
            for connector in self.connectors
            for cavity in connector.cavities
        }
        splice_ids = {item.id for item in self.splices}
        wire_type_ids = {item.id for item in self.wire_types}
        net_ids = {item.id for item in self.nets}
        route_ids = {item.id for item in self.routes}
        for connector in self.connectors:
            cavity_ids = [cavity.id for cavity in connector.cavities]
            if len(set(cavity_ids)) != len(cavity_ids):
                raise ValueError(f"connector {connector.id} cavity ids must be unique")
        for net in self.nets:
            if net.twisted_pair_with is not None and net.twisted_pair_with not in net_ids:
                raise ValueError(f"net {net.id} twisted pair references unknown net")
        for wire in self.wires:
            if wire.wire_type not in wire_type_ids or wire.net not in net_ids:
                raise ValueError(f"wire {wire.id} references unknown wire type or net")
            if wire.route is not None and wire.route not in route_ids:
                raise ValueError(f"wire {wire.id} references unknown route")
            for endpoint in (wire.from_endpoint, wire.to_endpoint):
                if endpoint.splice is not None:
                    if endpoint.splice not in splice_ids:
                        raise ValueError(f"wire {wire.id} references unknown splice")
                elif (
                    endpoint.connector not in connector_ids
                    or (
                        endpoint.connector,
                        endpoint.cavity,
                    )
                    not in cavities
                ):
                    raise ValueError(f"wire {wire.id} references unknown connector cavity")
        return self


def _load(path: Path) -> tuple[str, bytes]:
    try:
        raw = path.read_bytes()
        payload = raw.decode("utf-8")
        json.loads(payload)
        return payload, raw
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load import {path}: {exc}") from exc


def import_source(file: str | Path, workspace: Path) -> dict[str, object]:
    path = workspace_path(file, workspace)
    payload, raw = _load(path)
    suffixes = path.name
    if suffixes.endswith(".connectivity.json"):
        source = ConnectivitySource.model_validate_json(payload)
        system = "circuit"
        extracted: dict[str, object] = {
            "connectors": [connector.model_dump() for connector in source.connectors],
            "nets": [net.model_dump() for net in source.nets],
        }
    elif suffixes.endswith(".envelope.json"):
        source = EnvelopeSource.model_validate_json(payload)
        system = "mech"
        extracted = {"anchors": [anchor.model_dump() for anchor in source.anchors]}
    elif suffixes.endswith(".contract.json"):
        source = WireContract.model_validate_json(payload)
        system = "wire"
        wire_types = {item.id: item for item in source.wire_types}
        extracted = {
            "wires": [
                {
                    "id": wire.id,
                    "net": wire.net,
                    "length_m": wire.length_m,
                    "resistance_ohm_per_km": wire_types[wire.wire_type].resistance_ohm_per_km,
                    "ampacity_a": wire_types[wire.wire_type].ampacity_a,
                }
                for wire in source.wires
            ],
            "nets": [net.model_dump() for net in source.nets],
        }
    else:
        raise ValueError(
            "import filename must end in .connectivity.json, .envelope.json, or .contract.json"
        )
    return {
        "system": system,
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "extracted": extracted,
    }


def write_import_record(file: str | Path, workspace: Path, out_dir: Path) -> dict[str, object]:
    record = import_source(file, workspace)
    out_dir = workspace_path(out_dir, workspace)
    out_dir.mkdir(parents=True, exist_ok=True)
    reject_symlinks(out_dir)
    records_path = out_dir / "imports.json"
    records: list[object] = []
    if records_path.is_file():
        value = json.loads(records_path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            records = cast(list[object], value)
    records = [
        entry
        for entry in records
        if (mapping := _object_mapping(entry)) is None or mapping.get("path") != record["path"]
    ]
    records.append(record)
    records_path.write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return record
