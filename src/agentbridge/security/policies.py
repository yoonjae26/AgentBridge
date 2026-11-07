"""Approval policy profiles (SAFE / STANDARD / TRUSTED)."""

from __future__ import annotations

from dataclasses import dataclass

from agentbridge.config.settings import PolicyProfile


@dataclass(frozen=True)
class Policy:
    profile: PolicyProfile
    # Whether agents may modify files in their (isolated) workspace.
    agents_may_edit: bool
    # Executables that validation commands may invoke.
    allowed_executables: frozenset[str]
    # Python modules allowed after ``python -m``.
    allowed_python_modules: frozenset[str]
    # Merges into the primary branch always need human approval; this is fixed.
    merge_requires_approval: bool = True
    # Claude Code permission mode used for agents under this profile.
    claude_permission_mode: str = "acceptEdits"


_SAFE_MODULES = frozenset({"pytest", "ruff", "mypy", "pyright", "coverage", "unittest"})

_BASE_EXECUTABLES = frozenset({"python", "python3", "pytest", "ruff", "mypy", "pyright", "git"})


def build_policy(profile: PolicyProfile, extra_allowed: list[str] | None = None) -> Policy:
    extra = frozenset(extra_allowed or [])
    if profile is PolicyProfile.SAFE:
        # Read-only analysis: agents may not edit; only safe validation commands.
        return Policy(
            profile=profile,
            agents_may_edit=False,
            allowed_executables=_BASE_EXECUTABLES,
            allowed_python_modules=_SAFE_MODULES,
            claude_permission_mode="plan",
        )
    if profile is PolicyProfile.STANDARD:
        return Policy(
            profile=profile,
            agents_may_edit=True,
            allowed_executables=_BASE_EXECUTABLES | frozenset({"npm", "node", "make"}) | extra,
            allowed_python_modules=_SAFE_MODULES,
            claude_permission_mode="acceptEdits",
        )
    # TRUSTED: more automation only within explicitly configured limits. Protected
    # git/filesystem operations remain blocked by permissions.check_command().
    return Policy(
        profile=profile,
        agents_may_edit=True,
        allowed_executables=_BASE_EXECUTABLES
        | frozenset({"npm", "node", "make", "npx", "uv", "tox", "nox"})
        | extra,
        allowed_python_modules=_SAFE_MODULES | frozenset({"tox", "nox", "build"}),
        claude_permission_mode="acceptEdits",
    )
