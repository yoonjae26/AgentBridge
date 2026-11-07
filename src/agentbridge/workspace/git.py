"""Thin, policy-aware wrapper around the git CLI."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentbridge.errors import GitError, PolicyViolationError
from agentbridge.security.permissions import is_protected_git_operation

GIT_TIMEOUT = 120


@dataclass
class GitResult:
    returncode: int
    stdout: str
    stderr: str


class Git:
    """Runs git commands in ``cwd``. Protected operations are refused outright."""

    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd

    def run(self, *args: str, check: bool = True, env: dict[str, str] | None = None) -> GitResult:
        argv = ["git", *args]
        if is_protected_git_operation(argv):
            raise PolicyViolationError(f"Protected git operation refused: git {' '.join(args)}")
        try:
            completed = subprocess.run(
                argv,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=GIT_TIMEOUT,
                check=False,
                env=env,
            )
        except FileNotFoundError as exc:
            raise GitError("git executable not found", hint="Install Git and retry.") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitError(f"git {' '.join(args)} timed out") from exc
        result = GitResult(completed.returncode, completed.stdout, completed.stderr)
        if check and completed.returncode != 0:
            raise GitError(
                f"git {' '.join(args)} failed ({completed.returncode}): "
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
        return result

    def out(self, *args: str) -> str:
        return self.run(*args).stdout.strip()

    # Convenience queries -------------------------------------------------
    def is_repository(self) -> bool:
        result = self.run("rev-parse", "--is-inside-work-tree", check=False)
        return result.returncode == 0 and result.stdout.strip() == "true"

    def toplevel(self) -> Path:
        return Path(self.out("rev-parse", "--show-toplevel"))

    def has_commits(self) -> bool:
        return self.run("rev-parse", "--verify", "HEAD", check=False).returncode == 0

    def head(self) -> str:
        return self.out("rev-parse", "HEAD")

    def current_branch(self) -> str | None:
        result = self.run("symbolic-ref", "--short", "-q", "HEAD", check=False)
        return result.stdout.strip() or None

    def branch_exists(self, branch: str) -> bool:
        return (
            self.run(
                "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False
            ).returncode
            == 0
        )

    def status_porcelain(self, include_untracked: bool = True) -> list[str]:
        untracked = "--untracked-files=all" if include_untracked else "--untracked-files=no"
        output = self.run("status", "--porcelain", untracked).stdout
        return [line for line in output.splitlines() if line.strip()]

    def is_clean(self) -> bool:
        return not self.status_porcelain()


def git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return True
