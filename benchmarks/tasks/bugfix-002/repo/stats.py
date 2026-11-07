"""Basic statistics."""


def mean(values):
    """Arithmetic mean of a non-empty sequence."""
    values = list(values)
    if not values:
        raise ValueError("mean() of empty sequence")
    return sum(values) / len(values)


def median(values):
    """Median of a non-empty sequence of numbers."""
    ordered = sorted(values)
    return ordered[len(ordered) // 2]
