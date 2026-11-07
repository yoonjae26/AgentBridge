"""Duration helpers."""

import re

_DURATION = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")


def format_duration(seconds: int) -> str:
    """Format seconds as e.g. '1h30m' (zero units omitted, '0s' for zero)."""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    parts = [f"{v}{u}" for v, u in ((hours, "h"), (minutes, "m"), (secs, "s")) if v]
    return "".join(parts) or "0s"


def parse_duration(text: str) -> int:
    """Parse a duration like '1h30m' into seconds."""
    match = _DURATION.fullmatch(text)
    if not text or match is None:
        raise ValueError(f"invalid duration: {text!r}")
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds
