import math


def clamp(value, low, high):
    if low > high:
        raise ValueError("low must not exceed high")
    return max(low, min(value, high))


def lerp(start, end, fraction):
    return start + (end - start) * fraction


def gcd_list(numbers):
    result = 0
    for number in numbers:
        result = math.gcd(result, number)
    return result
