"""Path validation helpers (path traversal protection)."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from agentbridge.errors import PolicyViolationError

_SENSITIVE_PARTS = frozenset({".git", ".ssh", ".aws", ".gnupg", ".agentbridge"})
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def validate_relative_path(raw: str) -> str:
    """Validate a repository-relative path supplied by untrusted input.

    Returns the normalised POSIX form. Rejects absolute paths, drive letters,
    ``..`` components and paths into sensitive directories.
    """
    if not raw or "\x00" in raw:
        raise PolicyViolationError("Empty or invalid path")
    text = raw.replace("\\", "/")
    if text.startswith("/") or _WINDOWS_DRIVE.match(text):
        raise PolicyViolationError(f"Absolute paths are not allowed: {raw!r}")
    parts = PurePosixPath(text).parts
    if any(part == ".." for part in parts):
        raise PolicyViolationError(f"Path traversal is not allowed: {raw!r}")
    if any(part in _SENSITIVE_PARTS for part in parts):
        raise PolicyViolationError(f"Path points into a protected directory: {raw!r}")
    normalised = "/".join(p for p in parts if p not in ("", "."))
    if not normalised:
        raise PolicyViolationError(f"Path resolves to the repository root: {raw!r}")
    return normalised


def resolve_inside(root: Path, raw: str) -> Path:
    """Resolve an untrusted relative path and ensure it stays inside ``root``."""
    relative = validate_relative_path(raw)
    root_resolved = root.resolve()
    candidate = (root_resolved / relative).resolve()
    if not candidate.is_relative_to(root_resolved):
        raise PolicyViolationError(f"Path escapes the workspace: {raw!r}")
    return candidate


_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_length: int = 40) -> str:
    """Lowercase ASCII slug for branch and directory names."""
    slug = _SLUG.sub("-", text.lower()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug or "task"
