"""Small numeric helpers."""

import math


def clamp(value, low, high):
    """Limit ``value`` to the range [low, high] and return the result.

    Raises ValueError if ``low`` is greater than ``high``.
    """
    if low > high:
        raise ValueError("low must not exceed high")
    return max(low, min(value, high))


def lerp(start, end, fraction):
    """Linearly interpolate between ``start`` and ``end`` by ``fraction`` (0..1)."""
    return start + (end - start) * fraction


def gcd_list(numbers):
    """Return the greatest common divisor of all integers in ``numbers`` (0 if empty)."""
    result = 0
    for number in numbers:
        result = math.gcd(result, number)
    return result
