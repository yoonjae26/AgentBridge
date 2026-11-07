from pathlib import Path

import pytest

from agentbridge.errors import InvalidStateError
from agentbridge.workspace.conflicts import check_merge, find_overlaps
from agentbridge.workspace.diff import compute_diff
from agentbridge.workspace.git import Git
from agentbridge.workspace.integration import merge_branch
from agentbridge.workspace.manager import WorkspaceManager
from tests.conftest import git


@pytest.fixture
def manager(repo: Path) -> WorkspaceManager:
    return WorkspaceManager(repo, repo / ".agentbridge" / "worktrees", "agentbridge")


def test_worktree_lifecycle_preserves_primary_tree(repo: Path, manager: WorkspaceManager):
    # The developer has uncommitted work in the primary checkout.
    (repo / "README.md").write_text("# local edit\n", encoding="utf-8")
    base = git(repo, "rev-parse", "HEAD")
    ws = manager.create_worktree("r1-task-001", "Add feature")
    assert ws.kind == "git_worktree"
    assert ws.base_commit == base
    assert ws.branch == "agentbridge/r1-task-001-add-feature"
    assert (ws.path / "README.md").read_text(encoding="utf-8") == "# sample\n"

    (ws.path / "feature.py").write_text("X = 1\n", encoding="utf-8")
    head = manager.commit_changes(ws.path, "agent work")
    assert head is not None
    assert manager.commit_changes(ws.path, "nothing new") is None

    diff = compute_diff(ws.path, base)
    assert diff.paths == ["feature.py"]
    assert diff.files[0].status == "A" and diff.files[0].additions == 1

    # Primary checkout untouched: same branch, same local edit, no new file.
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert (repo / "README.md").read_text(encoding="utf-8") == "# local edit\n"
    assert not (repo / "feature.py").exists()
    # AgentBridge state is excluded from git status without touching .gitignore.
    assert ".agentbridge" not in git(repo, "status", "--porcelain")
    assert not (repo / ".gitignore").exists()


def test_worktree_creation_is_idempotent(manager: WorkspaceManager):
    first = manager.create_worktree("r1-task-001", "Thing")
    (first.path / "partial.txt").write_text("work in progress", encoding="utf-8")
    again = manager.create_worktree("r1-task-001", "Thing")
    assert again.path == first.path
    assert (again.path / "partial.txt").exists()  # recovery never discards work


def test_existing_branch_never_overwritten(repo: Path, manager: WorkspaceManager):
    git(repo, "branch", "agentbridge/r9-task-001-thing")
    with pytest.raises(InvalidStateError, match="already exists"):
        manager.create_worktree("r9-task-001", "Thing")


def test_dirty_worktree_not_removed(manager: WorkspaceManager):
    ws = manager.create_worktree("r1-task-001", "Thing")
    (ws.path / "untracked.txt").write_text("x", encoding="utf-8")
    with pytest.raises(InvalidStateError):
        manager.remove_worktree(ws.path)
    assert ws.path.exists()


def test_overlap_and_conflict_detection(repo: Path, manager: WorkspaceManager):
    a = manager.create_worktree("r1-task-001", "A")
    b = manager.create_worktree("r1-task-002", "B")
    (a.path / "README.md").write_text("# from A\n", encoding="utf-8")
    (b.path / "README.md").write_text("# from B\n", encoding="utf-8")
    manager.commit_changes(a.path, "A")
    manager.commit_changes(b.path, "B")
    overlaps = find_overlaps({"r1-task-001": {"README.md"}, "r1-task-002": {"README.md", "x"}})
    assert overlaps[0].paths == ("README.md",)
    assert check_merge(repo, "main", a.branch or "").clean
    git(repo, "merge", "--no-ff", "-m", "merge A", a.branch or "")
    conflict = check_merge(repo, "main", b.branch or "")
    assert conflict.supported and not conflict.clean
    assert "README.md" in conflict.conflicting_files
    result = merge_branch(repo, b.branch or "", "main", "merge B")
    assert not result.merged
    assert Git(repo).is_clean()  # aborted cleanly; nothing half-merged


def test_merge_refuses_dirty_primary_tree(repo: Path, manager: WorkspaceManager):
    ws = manager.create_worktree("r1-task-001", "A")
    (ws.path / "new.txt").write_text("x", encoding="utf-8")
    manager.commit_changes(ws.path, "A")
    (repo / "README.md").write_text("uncommitted user change\n", encoding="utf-8")
    with pytest.raises(InvalidStateError, match="uncommitted"):
        merge_branch(repo, ws.branch or "", "main", "merge")
    assert (repo / "README.md").read_text(encoding="utf-8") == "uncommitted user change\n"


def test_dependency_branch_merged_into_downstream(manager: WorkspaceManager):
    up = manager.create_worktree("r1-task-001", "Up")
    (up.path / "models.py").write_text("M = 1\n", encoding="utf-8")
    manager.commit_changes(up.path, "models")
    down = manager.create_worktree("r1-task-002", "Down", base_ref=up.branch)
    assert (down.path / "models.py").exists()


def test_worktree_respects_line_ending_config(tmp_path: Path):
    """No spurious changes and no repo-config edits when core.autocrlf is enabled."""
    repo = tmp_path / "crlf"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "T")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "core.autocrlf", "true")
    (repo / "a.txt").write_text("line one\nline two\n", encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    config_before = (repo / ".git" / "config").read_text(encoding="utf-8")
    manager = WorkspaceManager(repo, repo / ".agentbridge" / "worktrees", "agentbridge")
    ws = manager.create_worktree("r1-task-001", "Noop")
    assert manager.commit_changes(ws.path, "nothing changed") is None
    assert (repo / ".git" / "config").read_text(encoding="utf-8") == config_before
