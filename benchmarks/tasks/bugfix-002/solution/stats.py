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
    if not ordered:
        raise ValueError("median() of empty sequence")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2
