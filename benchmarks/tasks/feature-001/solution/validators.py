"""Input validators."""

import re

_USERNAME = re.compile(r"[a-z][a-z0-9_]{2,15}")
_LOCAL = re.compile(r"[A-Za-z0-9._%+-]+")
_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?")
_TLD = re.compile(r"[A-Za-z]{2,}")


def is_valid_username(name: str) -> bool:
    """Lowercase, starts with a letter, 3-16 characters of [a-z0-9_]."""
    return bool(_USERNAME.fullmatch(name))


def is_valid_email(address: str) -> bool:
    """Return True if ``address`` is a syntactically valid e-mail address."""
    if address.count("@") != 1:
        return False
    local, domain = address.split("@")
    if not _LOCAL.fullmatch(local):
        return False
    labels = domain.split(".")
    if len(labels) < 2 or not all(_LABEL.fullmatch(label) for label in labels):
        return False
    return bool(_TLD.fullmatch(labels[-1]))
