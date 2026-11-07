"""Shape geometry."""

import math


def area(shape):
    """Area of a shape dict: {'kind': 'circle', 'r': ...} or {'kind': 'rect', 'w', 'h'}."""
    kind = shape["kind"]
    if kind == "circle":
        return math.pi * shape["r"] ** 2
    if kind == "rect":
        return shape["w"] * shape["h"]
    raise ValueError(f"unknown shape: {kind}")
