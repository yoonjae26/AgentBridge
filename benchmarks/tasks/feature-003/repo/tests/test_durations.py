from durations import format_duration


def test_format():
    assert format_duration(5400) == "1h30m"
    assert format_duration(0) == "0s"
