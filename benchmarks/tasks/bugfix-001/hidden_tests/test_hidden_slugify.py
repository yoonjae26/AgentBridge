from textutils import slugify


def test_collapses_separators():
    assert slugify("Hello,  World!") == "hello-world"


def test_strips_edges():
    assert slugify("  --Python 3.12--  ") == "python-3-12"


def test_empty():
    assert slugify("") == ""


def test_plain():
    assert slugify("abc") == "abc"
