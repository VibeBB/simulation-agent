from __future__ import annotations

import pytest

from sim.expr import evaluate


def test_expression_evaluator_supports_declared_arithmetic() -> None:
    assert evaluate("sqrt(R1 ** 2 + abs(R2)) / pi", {"R1": 3, "R2": -4}) == pytest.approx(
        13**0.5 / 3.141592653589793
    )


@pytest.mark.parametrize(
    "expression",
    [
        "R1.real",
        "__import__('os')",
        "open('secret')",
        "[x for x in (1, 2)]",
        "lambda: 1",
        "1 / 0",
        "float('inf')",
    ],
)
def test_expression_evaluator_rejects_unsafe_or_invalid_syntax(expression: str) -> None:
    with pytest.raises(ValueError):
        evaluate(expression, {"R1": 1})
