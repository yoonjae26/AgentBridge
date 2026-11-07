"""Shape reports."""

from geometry import legacy_area


def total_area(shapes):
    total = 0.0
    for shape in shapes:
        if shape["kind"] == "circle":
            total += legacy_area("circle", shape["r"])
        else:
            total += legacy_area(shape["kind"], shape.get("w"), shape.get("h"))
    return total


def describe(shapes):
    return f"{len(shapes)} shapes, total area {total_area(shapes):.2f}"
