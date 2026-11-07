from pathlib import Path

import pytest

import geometry
import report

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_removed():
    assert not hasattr(geometry, "legacy_area")
    assert "legacy_area" not in (ROOT / "report.py").read_text(encoding="utf-8")


def test_describe_unchanged():
    shapes = [{"kind": "circle", "r": 1}, {"kind": "rect", "w": 2, "h": 3},
              {"kind": "circle", "r": 2.5}]
    assert report.describe(shapes) == "3 shapes, total area 28.78"
    assert report.describe([]) == "0 shapes, total area 0.00"


def test_unknown_shape():
    with pytest.raises(ValueError):
        report.total_area([{"kind": "hexagon"}])
