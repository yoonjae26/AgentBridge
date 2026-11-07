import inspect
from pathlib import Path

import pytest

import mathlib

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = [n for n, f in inspect.getmembers(mathlib, inspect.isfunction)
          if not n.startswith("_") and f.__module__ == "mathlib"]


def test_has_public_functions():
    assert set(PUBLIC) >= {"clamp", "lerp", "gcd_list"}


@pytest.mark.parametrize("name", ["clamp", "lerp", "gcd_list"])
def test_docstring(name):
    doc = inspect.getdoc(getattr(mathlib, name)) or ""
    assert len(doc) >= 20


def test_readme_usage():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Usage" in readme
    usage = readme.split("## Usage", 1)[1]
    assert "```python" in usage
    assert "mathlib" in usage


def test_behaviour_unchanged():
    assert mathlib.clamp(-1, 0, 3) == 0
    assert mathlib.lerp(2, 4, 0.5) == 3
    assert mathlib.gcd_list([]) == 0
    with pytest.raises(ValueError):
        mathlib.clamp(1, 3, 0)
