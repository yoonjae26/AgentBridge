import pytest

from stats import mean, median


def test_even():
    assert median([1, 2, 3, 4]) == 2.5


def test_even_unsorted():
    assert median([4, 1, 3, 2]) == 2.5


def test_single():
    assert median([5]) == 5


def test_empty_raises_value_error():
    with pytest.raises(ValueError):
        median([])


def test_mean_unchanged():
    assert mean([2, 4]) == 3
