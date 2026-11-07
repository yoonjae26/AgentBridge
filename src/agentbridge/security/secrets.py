"""Secret redaction for anything that is logged, persisted or reported.

Redaction is best-effort pattern matching. It reduces accidental exposure; it is
not a guarantee that arbitrary agent output is free of sensitive data.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping

REDACTED = "[REDACTED]"

_SENSITIVE_ENV_NAME = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|COOKIE|SESSION)", re.IGNORECASE
)

# Ordered from most to least specific.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),  # Anthropic
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}"),  # OpenAI-style
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),  # GitHub tokens
    re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),  # Google API key
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.=]{16,}"),
    re.compile(
        r"(?i)\b([A-Z0-9_]*(?:api[_-]?key|token|secret|password|passwd)[A-Z0-9_]*"
        r"\s*[=:]\s*)(['\"]?)[^\s'\"]{6,}\2"
    ),
)


def _env_secret_values(environ: Mapping[str, str] | None = None) -> list[str]:
    env = os.environ if environ is None else environ
    values = [
        value
        for name, value in env.items()
        if _SENSITIVE_ENV_NAME.search(name) and value and len(value) >= 8
    ]
    # Longest first so overlapping values are fully replaced.
    return sorted(set(values), key=len, reverse=True)


def redact(text: str, extra_secrets: Iterable[str] = (), *, use_env: bool = True) -> str:
    """Return ``text`` with known credential formats and env secret values replaced."""
    if not text:
        return text
    result = text
    literal_values = list(extra_secrets)
    if use_env:
        literal_values.extend(_env_secret_values())
    for value in sorted({v for v in literal_values if v and len(v) >= 8}, key=len, reverse=True):
        result = result.replace(value, REDACTED)
    for pattern in _PATTERNS:
        if (
            pattern.groups >= 1 and pattern.pattern.startswith("(?i)(bearer")
        ) or pattern.groups >= 2:
            result = pattern.sub(lambda m: m.group(1) + REDACTED, result)
        else:
            result = pattern.sub(REDACTED, result)
    return result


def contains_secret(text: str) -> bool:
    """True if ``text`` matches a known credential pattern (env values ignored)."""
    return redact(text, use_env=False) != text


def safe_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment for child processes.

    Provider CLIs need their own credentials (e.g. ``ANTHROPIC_API_KEY``), so the
    environment is passed through; this hook exists so policy can restrict it later
    and so we never *add* secrets to a child environment.
    """
    return dict(os.environ if base is None else base)
