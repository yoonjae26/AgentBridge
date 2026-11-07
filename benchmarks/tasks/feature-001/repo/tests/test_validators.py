from validators import is_valid_username


def test_valid_username():
    assert is_valid_username("alice_01")


def test_invalid_username():
    assert not is_valid_username("1alice")
