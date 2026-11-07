from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text():
    path = ROOT / "ANALYSIS.md"
    assert path.exists(), "ANALYSIS.md was not written"
    return path.read_text(encoding="utf-8")


def test_modules_listed():
    content = text()
    for module in ("cart", "pricing", "tax", "cli"):
        assert module in content


def test_functions_listed():
    content = text()
    for name in ("add_item", "remove_item", "item_count", "apply_discount", "round_price",
                 "tax_for"):
        assert name in content


def test_entry_point():
    assert "main" in text()


def test_untested_modules():
    lines = [line.lower() for line in text().splitlines() if "untested" in line.lower()]
    for module in ("pricing", "tax", "cli"):
        assert any(module in line for line in lines), module
    assert not any("cart" in line for line in lines)
