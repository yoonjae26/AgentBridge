"""Small text helpers."""

import re


def slugify(text: str) -> str:
    """Convert text to a URL slug: lowercase words joined by single dashes."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
