"""Touchstone v1 reader for S-parameter band checks."""

from __future__ import annotations

import cmath
import math
import re
from dataclasses import dataclass
from pathlib import Path

_FREQUENCY = {"HZ": 1.0, "KHZ": 1e3, "MHZ": 1e6, "GHZ": 1e9}


@dataclass(frozen=True)
class TouchstoneSample:
    frequency_hz: float
    matrix: tuple[tuple[complex, ...], ...]


@dataclass(frozen=True)
class TouchstoneData:
    ports: int
    reference_ohm: float
    samples: tuple[TouchstoneSample, ...]
    non_passive: bool


def _complex(a: float, b: float, fmt: str) -> complex:
    if fmt == "RI":
        return complex(a, b)
    if fmt == "MA":
        return cmath.rect(a, math.radians(b))
    try:
        magnitude = 10 ** (a / 20)
    except OverflowError as exc:
        raise ValueError("Touchstone magnitude is not finite") from exc
    return cmath.rect(magnitude, math.radians(b))


def parse(path: Path) -> TouchstoneData:
    match = re.search(r"\.s(\d+)p$", path.name, re.IGNORECASE)
    if not match:
        raise ValueError("Touchstone filename must end in .sNp")
    ports = int(match.group(1))
    unit, fmt, reference = "HZ", "MA", 50.0
    option_seen = False
    tokens: list[float] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("!", 1)[0].strip()
        if not line:
            continue
        if line.startswith("#"):
            if option_seen:
                raise ValueError("Touchstone file must have exactly one option line")
            fields = line[1:].upper().split()
            if len(fields) < 5 or fields[1] != "S" or fields[2] not in ("MA", "DB", "RI"):
                raise ValueError(f"unsupported Touchstone option line: {line}")
            unit, fmt = fields[0], fields[2]
            if unit not in _FREQUENCY:
                raise ValueError(f"unsupported frequency unit {unit!r}")
            if fields[3] != "R":
                raise ValueError("Touchstone option line must include R reference")
            reference = float(fields[4])
            if not math.isfinite(reference) or reference <= 0:
                raise ValueError("Touchstone reference impedance must be finite and positive")
            option_seen = True
            continue
        tokens.extend(float(item) for item in line.split())
    if not option_seen:
        raise ValueError("Touchstone option line is missing")
    stride = 1 + 2 * ports * ports
    if not tokens or len(tokens) % stride:
        raise ValueError("Touchstone data has incomplete network rows")
    samples: list[TouchstoneSample] = []
    non_passive = False
    for start in range(0, len(tokens), stride):
        row = tokens[start : start + stride]
        frequency = row[0] * _FREQUENCY[unit]
        values = [_complex(row[index], row[index + 1], fmt) for index in range(1, stride, 2)]
        matrix = tuple(
            tuple(values[column * ports + row_index] for column in range(ports))
            for row_index in range(ports)
        )
        if (
            not math.isfinite(frequency)
            or frequency < 0
            or any(
                not math.isfinite(value.real) or not math.isfinite(value.imag)
                for matrix_row in matrix
                for value in matrix_row
            )
        ):
            raise ValueError("Touchstone contains non-finite or negative-frequency data")
        if any(
            any(abs(matrix[row_index][col]) > 1.0 + 1e-6 for row_index in range(ports))
            or sum(abs(matrix[row_index][col]) ** 2 for row_index in range(ports)) > 1.001
            for col in range(ports)
        ):
            non_passive = True
        samples.append(TouchstoneSample(frequency, matrix))
    return TouchstoneData(ports, reference, tuple(samples), non_passive)
