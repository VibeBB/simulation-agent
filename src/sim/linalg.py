"""Small dense linear solver used by electrical and thermal networks."""

from __future__ import annotations

import math


def solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    if size == 0 or len(matrix) != size or any(len(row) != size for row in matrix):
        raise ValueError("matrix must be non-empty and square")
    if any(
        not math.isfinite(value)
        for row, rhs in zip(matrix, vector, strict=True)
        for value in (*row, rhs)
    ):
        raise ValueError("matrix contains non-finite values")
    a = [[*row, value] for row, value in zip(matrix, vector, strict=True)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda row: abs(a[row][col]))
        scale = max(abs(value) for value in a[pivot][:-1])
        if abs(a[pivot][col]) <= max(1.0, scale) * 1e-14:
            raise ValueError("singular matrix")
        a[col], a[pivot] = a[pivot], a[col]
        divisor = a[col][col]
        a[col] = [value / divisor for value in a[col]]
        for row in range(size):
            if row == col:
                continue
            factor = a[row][col]
            if factor:
                a[row] = [x - factor * y for x, y in zip(a[row], a[col], strict=True)]
    result = [row[-1] for row in a]
    if any(not math.isfinite(value) for value in result):
        raise ValueError("non-finite solution")
    return result
