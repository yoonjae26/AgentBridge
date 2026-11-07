from textutils import slugify


def test_simple_word():
    assert slugify("hello") == "hello"


def test_lowercases():
    assert slugify("Hello") == "hello"
