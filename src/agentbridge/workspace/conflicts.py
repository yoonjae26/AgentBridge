"""Overlap and merge-conflict detection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agentbridge.workspace.git import Git


@dataclass(frozen=True)
class Overlap:
    first: str
    second: str
    paths: tuple[str, ...]


def find_overlaps(changesets: Mapping[str, set[str]]) -> list[Overlap]:
    """Pairs of tasks that modified the same files."""
    items = sorted(changesets.items())
    overlaps: list[Overlap] = []
    for i, (first, first_paths) in enumerate(items):
        for second, second_paths in items[i + 1 :]:
            common = first_paths & second_paths
            if common:
                overlaps.append(Overlap(first, second, tuple(sorted(common))))
    return overlaps


@dataclass(frozen=True)
class MergeCheck:
    clean: bool
    conflicting_files: tuple[str, ...]
    supported: bool = True
    message: str = ""


def check_merge(repo: Path, target: str, branch: str) -> MergeCheck:
    """Dry-run merge using ``git merge-tree --write-tree`` (git >= 2.38).

    Does not touch the working tree or index.
    """
    git = Git(repo)
    result = git.run(
        "merge-tree", "--write-tree", "--name-only", "--no-messages", target, branch, check=False
    )
    if result.returncode == 0:
        return MergeCheck(clean=True, conflicting_files=())
    if result.returncode == 1:
        lines = [line for line in result.stdout.splitlines()[1:] if line.strip()]
        return MergeCheck(clean=False, conflicting_files=tuple(lines))
    return MergeCheck(
        clean=False,
        conflicting_files=(),
        supported=False,
        message=result.stderr.strip() or "git merge-tree failed (requires git >= 2.38)",
    )
