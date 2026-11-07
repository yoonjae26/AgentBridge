import pytest

from durations import format_duration, parse_duration


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1h30m", 5400), ("45s", 45), ("2h5s", 7205), ("10m", 600), ("1h1m1s", 3661)],
)
def test_valid(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "1x", "30m1h", "-5m", "1h 30m", "h"])
def test_invalid(text):
    with pytest.raises(ValueError):
        parse_duration(text)


def test_round_trip():
    assert parse_duration(format_duration(3725)) == 3725
