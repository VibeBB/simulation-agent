"""Safe arithmetic expression evaluator for WCA."""

from __future__ import annotations

import ast
import math
from collections.abc import Callable

_BINOPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.Pow: math.pow,
}
_FUNCS = {
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "min": min,
    "max": max,
}


def evaluate(expression: str, values: dict[str, float]) -> float:
    try:
        tree = ast.parse(expression, mode="eval")
        result = _evaluate(tree.body, values)
    except (ArithmeticError, SyntaxError, TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"invalid expression: {exc}") from exc
    if not math.isfinite(result):
        raise ValueError("expression produced a non-finite result")
    return result


def _evaluate(node: ast.expr, values: dict[str, float]) -> float:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id == "pi":
            return math.pi
        if node.id not in values:
            raise ValueError(f"unknown name {node.id!r}")
        return float(values[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_evaluate(node.left, values), _evaluate(node.right, values))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate(node.operand, values)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        if node.keywords:
            raise ValueError("keyword arguments are not allowed")
        return float(_FUNCS[node.func.id](*(_evaluate(arg, values) for arg in node.args)))
    raise ValueError(f"unsupported expression syntax: {type(node).__name__}")
