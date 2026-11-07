import pytest

from validators import is_valid_email, is_valid_username

VALID = ["user@example.com", "first.last+tag@sub.example.org", "a_b%c-d@x-y.io"]
INVALID = [
    "plainaddress", "@example.com", "user@", "user@example", "user@@example.com",
    "user name@example.com", "user@-example.com", "user@example-.com", "user@example.c",
    "user@exa_mple.com", "user@.example.com", "",
]


@pytest.mark.parametrize("address", VALID)
def test_valid(address):
    assert is_valid_email(address) is True


@pytest.mark.parametrize("address", INVALID)
def test_invalid(address):
    assert is_valid_email(address) is False


def test_username_unchanged():
    assert is_valid_username("alice_01")
