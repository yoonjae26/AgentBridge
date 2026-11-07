"""Input validators."""

import re

_USERNAME = re.compile(r"[a-z][a-z0-9_]{2,15}")


def is_valid_username(name: str) -> bool:
    """Lowercase, starts with a letter, 3-16 characters of [a-z0-9_]."""
    return bool(_USERNAME.fullmatch(name))
