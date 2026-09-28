from __future__ import annotations

from pathlib import Path

import pytest

from sim.analysis import microstrip_impedance
from sim.touchstone import parse


def test_touchstone_two_port_and_passivity(tmp_path: Path) -> None:
    path = tmp_path / "divider.s2p"
    path.write_text(
        "# GHz S RI R 50\n1 0.1 0 0.8 0 0.8 0 0.1 0\n2 0.1 0 0.8 0 0.8 0 0.1 0\n",
        encoding="utf-8",
    )

    data = parse(path)
    assert data.ports == 2
    assert data.reference_ohm == 50
    assert data.samples[0].frequency_hz == 1e9
    assert data.samples[0].matrix[1][0] == 0.8 + 0j
    assert not data.non_passive


def test_touchstone_rejects_duplicate_option_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.s1p"
    path.write_text(
        "# GHz S RI R 50\n# GHz S RI R 50\n1 0.1 0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly one option line"):
        parse(path)


@pytest.mark.parametrize(
    ("format_name", "data", "expected"),
    [
        ("MA", "0.5 90", 0.5j),
        ("DB", "-6.020599913 0", 0.5 + 0j),
        ("RI", "0.3 0.4", 0.3 + 0.4j),
    ],
)
def test_touchstone_single_port_formats(
    tmp_path: Path, format_name: str, data: str, expected: complex
) -> None:
    path = tmp_path / f"single-{format_name}.s1p"
    path.write_text(f"# MHz S {format_name} R 50\n100 {data}\n", encoding="utf-8")

    sample = parse(path).samples[0]

    assert sample.frequency_hz == 100e6
    assert sample.matrix[0][0] == pytest.approx(expected)


def test_touchstone_accepts_multiline_two_port_rows_and_marks_nonpassive_data(
    tmp_path: Path,
) -> None:
    multiline = tmp_path / "multiline.s2p"
    multiline.write_text(
        "# Hz S RI R 50\n1 0 0 0.1 0 0.2 0 0.3 0\n2 0.4 0 0.5 0 0.6 0 0.7 0\n",
        encoding="utf-8",
    )
    non_passive = tmp_path / "non-passive.s1p"
    non_passive.write_text("# Hz S RI R 50\n1 1.01 0\n", encoding="utf-8")

    data = parse(multiline)

    assert len(data.samples) == 2
    assert data.samples[0].matrix == ((0j, 0.2 + 0j), (0.1 + 0j, 0.3 + 0j))
    assert parse(non_passive).non_passive


def test_touchstone_rejects_db_values_that_overflow_float_range(tmp_path: Path) -> None:
    path = tmp_path / "overflow.s1p"
    path.write_text("# Hz S DB R 50\n1 1e308 0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="magnitude is not finite"):
        parse(path)


def test_microstrip_estimate_is_physical() -> None:
    impedance = microstrip_impedance(2.9, 1.6, 35, 4.4)
    assert 45 < impedance < 55
