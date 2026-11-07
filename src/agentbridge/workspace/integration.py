"""Integration (merge) of approved task branches into the primary branch.

Only ever invoked after explicit human approval. Never force-pushes, never
resets, and refuses to run when the developer's working tree has changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentbridge.errors import GitError, InvalidStateError
from agentbridge.workspace.conflicts import check_merge
from agentbridge.workspace.git import Git
from agentbridge.workspace.manager import _identity_args


@dataclass(frozen=True)
class MergeResult:
    merged: bool
    commit: str | None
    message: str


def merge_branch(repo_root: Path, branch: str, target_branch: str, message: str) -> MergeResult:
    git = Git(repo_root)
    current = git.current_branch()
    if current != target_branch:
        raise InvalidStateError(
            f"Primary checkout is on {current!r}, expected {target_branch!r}",
            hint=f"Run 'git switch {target_branch}' in {repo_root} and approve again.",
        )
    # Untracked files are left alone: git itself refuses a merge that would
    # overwrite them, so only tracked modifications block integration.
    dirty = git.status_porcelain(include_untracked=False)
    if dirty:
        raise InvalidStateError(
            "The primary working tree has uncommitted changes; refusing to merge",
            hint="Commit or stash your own changes first. AgentBridge never overwrites them.",
        )
    if not git.branch_exists(branch):
        raise GitError(f"Task branch {branch} does not exist")
    check = check_merge(repo_root, target_branch, branch)
    if check.supported and not check.clean:
        return MergeResult(
            merged=False,
            commit=None,
            message="Merge would conflict in: " + ", ".join(check.conflicting_files),
        )
    result = git.run(*_identity_args(), "merge", "--no-ff", "-m", message, branch, check=False)
    if result.returncode != 0:
        git.run("merge", "--abort", check=False)
        return MergeResult(False, None, f"Merge failed and was aborted: {result.stderr.strip()}")
    return MergeResult(True, git.head(), f"Merged {branch} into {target_branch}")
