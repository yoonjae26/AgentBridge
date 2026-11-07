import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def review_text():
    path = ROOT / "REVIEW.md"
    assert path.exists(), "REVIEW.md was not written"
    return path.read_text(encoding="utf-8").lower()


def test_identifies_sql_injection():
    text = review_text()
    assert "find_user" in text
    assert re.search(r"sql[ -]?injection|injection", text)


def test_identifies_password_comparison():
    text = review_text()
    assert "check_password" in text
    assert re.search(r"constant[- ]time|timing|compare_digest|plain ?text|hash", text)


def test_source_unchanged():
    content = (ROOT / "accounts.py").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(content).hexdigest() == "0bc4276f7ed8cb5f6a9b9a8adfe45674021b71f99c8f40ace693b4dee6d39135"
