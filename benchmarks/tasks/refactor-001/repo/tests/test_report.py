from report import describe

SHAPES = [{"kind": "circle", "r": 1}, {"kind": "rect", "w": 2, "h": 3}]


def test_describe():
    assert describe(SHAPES) == "2 shapes, total area 9.14"
