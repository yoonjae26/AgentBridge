import pytest

from pagination import page_count, paginate

ITEMS = list(range(25))


def test_first_page():
    assert paginate(ITEMS, 1, 10) == list(range(10))


def test_last_partial_page():
    assert paginate(ITEMS, 3, 10) == [20, 21, 22, 23, 24]


def test_page_count_rounds_up():
    assert page_count(25, 10) == 3


def test_page_count_exact_and_zero():
    assert page_count(20, 10) == 2
    assert page_count(0, 10) == 0


def test_invalid_page():
    with pytest.raises(ValueError):
        paginate(ITEMS, 0)
