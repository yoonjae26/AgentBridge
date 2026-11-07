"""Workspace management: isolated git worktrees per task.

A git worktree isolates *changes*; it is not a security sandbox. Agents run with
the same OS permissions as the user.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from agentbridge.errors import GitError, InvalidStateError
from agentbridge.security.paths import slugify
from agentbridge.workspace.git import Git

AGENT_IDENTITY = ("AgentBridge", "agentbridge@localhost")

# Tool caches that must never be committed as "agent changes" or count as
# uncommitted work. Excluded with pathspecs, so no user git config is modified.
TOOL_NOISE_DIRS = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache")
_NOISE_PATHSPECS = [f":(exclude,glob)**/{name}/**" for name in TOOL_NOISE_DIRS]


def without_tool_noise(porcelain_lines: list[str]) -> list[str]:
    """Drop ``git status --porcelain`` lines that only concern tool caches."""
    kept = []
    for line in porcelain_lines:
        path = line[3:].strip().strip('"').replace("\\", "/")
        if not any(part in TOOL_NOISE_DIRS for part in path.split("/")):
            kept.append(line)
    return kept


@dataclass(frozen=True)
class Workspace:
    path: Path
    kind: str  # "git_worktree" | "directory"
    branch: str | None
    base_branch: str | None
    base_commit: str | None


def _identity_args() -> list[str]:
    name, email = AGENT_IDENTITY
    return ["-c", f"user.name={name}", "-c", f"user.email={email}", "-c", "commit.gpgsign=false"]


def ensure_state_dir_excluded(repo_root: Path, pattern: str = ".agentbridge/") -> None:
    """Hide AgentBridge state from ``git status`` without editing tracked files.

    Uses ``.git/info/exclude`` so the user's ``.gitignore`` is never modified.
    """
    git = Git(repo_root)
    common_dir = Path(git.out("rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = (repo_root / common_dir).resolve()
    exclude = common_dir / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if pattern not in existing.splitlines():
        with exclude.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(f"# added by agentbridge\n{pattern}\n")


class WorkspaceManager:
    def __init__(self, repo_root: Path, worktrees_dir: Path, branch_prefix: str) -> None:
        self.repo_root = repo_root.resolve()
        self.worktrees_dir = worktrees_dir.resolve()
        self.branch_prefix = branch_prefix
        self.git = Git(self.repo_root)

    # ------------------------------------------------------------- helpers
    def branch_name(self, task_id: str, title: str) -> str:
        branch = f"{self.branch_prefix}/{task_id}-{slugify(title, 30)}"
        result = self.git.run("check-ref-format", "--branch", branch, check=False)
        if result.returncode != 0:
            branch = f"{self.branch_prefix}/{re.sub(r'[^a-z0-9-]', '-', task_id)}"
        return branch

    def require_repository(self) -> None:
        if not self.git.is_repository():
            raise GitError(
                f"{self.repo_root} is not a git repository",
                hint="Run 'git init' and create an initial commit, or set "
                "workspace.use_git_worktree: false.",
            )
        if not self.git.has_commits():
            raise GitError(
                "The repository has no commits; a worktree needs a base commit",
                hint="Create an initial commit first (git add -A && git commit -m 'init').",
            )

    def _registered_worktrees(self) -> dict[Path, str | None]:
        output = self.git.out("worktree", "list", "--porcelain")
        result: dict[Path, str | None] = {}
        current: Path | None = None
        for line in output.splitlines():
            if line.startswith("worktree "):
                current = Path(line[len("worktree ") :]).resolve()
                result[current] = None
            elif line.startswith("branch ") and current is not None:
                result[current] = line[len("branch ") :].removeprefix("refs/heads/")
        return result

    # ----------------------------------------------------------- lifecycle
    def create_worktree(
        self,
        task_id: str,
        title: str,
        base_ref: str | None = None,
        merge_branches: list[str] | None = None,
    ) -> Workspace:
        """Create (or idempotently reuse) the worktree for ``task_id``."""
        self.require_repository()
        ensure_state_dir_excluded(self.repo_root)
        base_branch = self.git.current_branch()
        base_commit = self.git.out("rev-parse", base_ref or "HEAD")
        branch = self.branch_name(task_id, title)
        path = self.worktrees_dir / task_id
        registered = self._registered_worktrees()
        if path.resolve() in registered:
            if registered[path.resolve()] != branch:
                raise InvalidStateError(
                    f"Worktree {path} exists but is on branch {registered[path.resolve()]}"
                )
            # Reuse: recovering an existing workspace must never discard work.
            return Workspace(path, "git_worktree", branch, base_branch, base_commit)
        if path.exists() and any(path.iterdir()):
            raise InvalidStateError(
                f"Workspace directory {path} exists and is not a registered worktree",
                hint="Inspect it manually; AgentBridge will not delete it.",
            )
        if self.git.branch_exists(branch):
            raise InvalidStateError(
                f"Branch {branch} already exists",
                hint="AgentBridge never overwrites existing branches.",
            )
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        # The worktree inherits the user's git configuration (e.g. core.autocrlf);
        # AgentBridge never changes repository config.
        self.git.run("worktree", "add", "-b", branch, str(path), base_commit)
        for other in merge_branches or []:
            self.merge_into_worktree(path, other)
        return Workspace(path, "git_worktree", branch, base_branch, base_commit)

    def merge_into_worktree(self, path: Path, branch: str) -> None:
        """Bring a dependency's branch into a task worktree; abort on conflict."""
        git = Git(path)
        result = git.run(*_identity_args(), "merge", "--no-ff", "--no-edit", branch, check=False)
        if result.returncode != 0:
            git.run("merge", "--abort", check=False)
            raise GitError(
                f"Dependency branch {branch} conflicts with the task workspace: "
                f"{result.stdout.strip() or result.stderr.strip()}"
            )

    def create_directory_workspace(self, task_id: str) -> Workspace:
        """Fallback when git worktrees are disabled: a private scratch git repo."""
        path = self.worktrees_dir / task_id
        path.mkdir(parents=True, exist_ok=True)
        git = Git(path)
        if not (path / ".git").exists():
            git.run("init", "-q")
            git.run("config", "core.autocrlf", "false")
            git.run(*_identity_args(), "commit", "--allow-empty", "-q", "-m", "workspace base")
        return Workspace(path, "directory", git.current_branch(), None, git.head())

    def commit_changes(self, path: Path, message: str) -> str | None:
        """Commit everything the agent changed. Returns the new commit or None."""
        git = Git(path)
        git.run("add", "-A", "--", ".", *_NOISE_PATHSPECS)
        if git.run("diff", "--cached", "--quiet", check=False).returncode == 0:
            return None
        env = dict(os.environ)
        git.run(*_identity_args(), "commit", "-q", "--no-verify", "-m", message, env=env)
        return git.head()

    def remove_worktree(self, path: Path) -> None:
        """Remove a clean worktree. Dirty worktrees are never removed."""
        git = Git(path)
        if without_tool_noise(git.status_porcelain()):
            raise InvalidStateError(
                f"Worktree {path} has uncommitted changes; refusing to remove it"
            )
        self.git.run("worktree", "remove", str(path))
