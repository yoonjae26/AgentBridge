"""Duration helpers."""


def format_duration(seconds: int) -> str:
    """Format seconds as e.g. '1h30m' (zero units omitted, '0s' for zero)."""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    parts = [f"{v}{u}" for v, u in ((hours, "h"), (minutes, "m"), (secs, "s")) if v]
    return "".join(parts) or "0s"


def parse_duration(text: str) -> int:
    """Parse a duration like '1h30m' into seconds."""
    raise NotImplementedError
