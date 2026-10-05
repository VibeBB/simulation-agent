"""Parser for ngspice binary raw files (-r raw.bin).

A raw file holds one or more concatenated plot blocks. Each block is an
ASCII header (``Title``, ``Date``, ``Plotname``, ``Flags``, ``No.
Variables``, ``No. Points``, a ``Variables:`` table, then ``Binary:``)
followed by little-endian float64 data: per point, every variable in
order; a ``complex`` flag doubles each value into a (real, imag) pair.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RawPlot:
    title: str
    plotname: str
    complex_values: bool
    variables: tuple[str, ...]
    points: int
    # data[i] is variable i's series; complex plots store complex numbers.
    data: tuple[tuple[complex | float, ...], ...]

    @property
    def scale_name(self) -> str:
        return self.variables[0] if self.variables else ""


def parse_raw_bytes(blob: bytes) -> list[RawPlot]:
    plots: list[RawPlot] = []
    offset = 0
    size = len(blob)
    while offset < size:
        marker = blob.find(b"Binary:", offset)
        if marker < 0:
            break
        header = blob[offset:marker].decode("ascii", errors="replace")
        fields: dict[str, str] = {}
        variables: list[str] = []
        in_variables = False
        for line in header.splitlines():
            line = line.strip("\x00").rstrip()
            if not line:
                continue
            if line == "Variables:":
                in_variables = True
                continue
            if in_variables:
                parts = line.split()
                if len(parts) >= 2:
                    variables.append(parts[1])
                continue
            key, _, value = line.partition(":")
            if key.strip() in {
                "Title",
                "Date",
                "Plotname",
                "Flags",
                "No. Variables",
                "No. Points",
            }:
                fields[key.strip()] = value.strip()
        try:
            n_vars = int(fields["No. Variables"])
            n_points = int(fields["No. Points"])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"raw plot header is incomplete: {exc}") from exc
        if variables and len(variables) != n_vars:
            raise ValueError("raw plot variable table does not match No. Variables")
        if not variables:
            raise ValueError("raw plot is missing the Variables table")
        is_complex = "complex" in fields.get("Flags", "").lower()
        width = 2 if is_complex else 1
        count = n_vars * n_points * width
        start = marker + len(b"Binary:")
        # Skip line termination after "Binary:".
        while start < size and blob[start] in b"\r\n":
            start += 1
        needed = count * 8
        if start + needed > size:
            raise ValueError("raw plot binary payload is truncated")
        values = struct.unpack(f"<{count}d", blob[start : start + needed])
        series: list[tuple[complex | float, ...]] = []
        for var in range(n_vars):
            column: list[complex | float] = []
            for point in range(n_points):
                base = (point * n_vars + var) * width
                if is_complex:
                    column.append(complex(values[base], values[base + 1]))
                else:
                    column.append(values[base])
            series.append(tuple(column))
        plots.append(
            RawPlot(
                title=fields.get("Title", ""),
                plotname=fields.get("Plotname", ""),
                complex_values=is_complex,
                variables=tuple(variables),
                points=n_points,
                data=tuple(series),
            )
        )
        offset = start + needed
    if not plots:
        raise ValueError("no plot blocks found in raw file")
    return plots


def parse_raw(path: Path) -> list[RawPlot]:
    return parse_raw_bytes(path.read_bytes())
