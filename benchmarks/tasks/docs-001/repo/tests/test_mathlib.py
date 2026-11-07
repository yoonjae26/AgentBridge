from mathlib import clamp, gcd_list, lerp


def test_clamp():
    assert clamp(5, 0, 3) == 3


def test_lerp():
    assert lerp(0, 10, 0.5) == 5


def test_gcd_list():
    assert gcd_list([12, 18, 24]) == 6
