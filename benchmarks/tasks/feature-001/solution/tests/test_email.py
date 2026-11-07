from validators import is_valid_email


def test_valid():
    assert is_valid_email("user@example.com")


def test_invalid():
    assert not is_valid_email("user@example")
