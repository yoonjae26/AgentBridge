import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def requirements():
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def version_tuple(text):
    return tuple(int(p) for p in text.split("."))


def test_requests_minimum():
    line = next(r for r in requirements() if r.lower().startswith("requests"))
    match = re.search(r"(==|>=|~=)\s*([0-9]+(?:\.[0-9]+)*)", line)
    assert match, line
    assert version_tuple(match.group(2)) >= (2, 32, 3)


def test_other_pins_unchanged():
    others = [r for r in requirements() if not r.lower().startswith("requests")]
    assert others == ["click==8.1.7", "PyYAML==6.0.1"]


def test_changelog():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = text.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "requests" in unreleased.lower()
