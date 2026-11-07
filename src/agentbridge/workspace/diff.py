"""Diff capture for task workspaces."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from agentbridge.security.secrets import redact
from agentbridge.workspace.git import Git

MAX_PATCH_CHARS = 200_000


class FileChange(BaseModel):
    path: str
    status: str  # A, M, D, R, ...
    additions: int | None = None  # None for binary files
    deletions: int | None = None


class DiffSummary(BaseModel):
    base: str
    head: str
    files: list[FileChange] = Field(default_factory=list)
    patch: str = ""
    patch_truncated: bool = False

    @property
    def paths(self) -> list[str]:
        return [f.path for f in self.files]

    @property
    def is_empty(self) -> bool:
        return not self.files


def compute_diff(workdir: Path, base: str, head: str = "HEAD") -> DiffSummary:
    git = Git(workdir)
    head_sha = git.out("rev-parse", head)
    statuses: dict[str, str] = {}
    for line in git.out("diff", "--name-status", "--no-renames", base, head_sha).splitlines():
        if not line.strip():
            continue
        status, _, path = line.partition("\t")
        statuses[path] = status.strip()
    numstats: dict[str, tuple[int | None, int | None]] = {}
    for line in git.out("diff", "--numstat", "--no-renames", base, head_sha).splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            add, delete, path = parts
            numstats[path] = (
                int(add) if add.isdigit() else None,
                int(delete) if delete.isdigit() else None,
            )
    files = [
        FileChange(
            path=path,
            status=status,
            additions=numstats.get(path, (None, None))[0],
            deletions=numstats.get(path, (None, None))[1],
        )
        for path, status in sorted(statuses.items())
    ]
    patch = git.run("diff", "--no-renames", base, head_sha).stdout
    truncated = len(patch) > MAX_PATCH_CHARS
    if truncated:
        patch = patch[:MAX_PATCH_CHARS]
    return DiffSummary(
        base=base, head=head_sha, files=files, patch=redact(patch), patch_truncated=truncated
    )
