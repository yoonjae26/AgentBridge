"""Shape reports."""

from geometry import area


def total_area(shapes):
    return float(sum(area(shape) for shape in shapes))


def describe(shapes):
    return f"{len(shapes)} shapes, total area {total_area(shapes):.2f}"
