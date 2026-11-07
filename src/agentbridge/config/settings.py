"""Typed, validated configuration models (``agentbridge.yaml``)."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIG_FILENAME = "agentbridge.yaml"
STATE_DIRNAME = ".agentbridge"

_PROVIDER_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

# Provider adapter types shipped with AgentBridge. A provider entry whose key
# matches one of these names gets that type by default.
KNOWN_PROVIDER_TYPES = ("mock", "claude_code", "antigravity_remote", "generic_cli")
_DEFAULT_TYPE_BY_NAME = {
    "mock": "mock",
    "claude": "claude_code",
    "claude_code": "claude_code",
    "antigravity": "antigravity_remote",
}


class PolicyProfile(StrEnum):
    SAFE = "safe"
    STANDARD = "standard"
    TRUSTED = "trusted"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ProjectSettings(_Strict):
    name: str = "my-project"
    repository: str = "."
    default_branch: str = "main"


class OrchestrationSettings(_Strict):
    max_parallel_tasks: int = Field(default=2, ge=1, le=16)
    retry_limit: int = Field(default=2, ge=0, le=10)
    retry_backoff_seconds: float = Field(default=2.0, ge=0, le=300)
    task_timeout_seconds: int = Field(default=1800, ge=1, le=86_400)
    require_approval_before_merge: bool = True
    planner_mode: Literal["single", "standard", "provider"] = "single"
    heartbeat_seconds: float = Field(default=5.0, gt=0, le=300)
    stale_after_seconds: float = Field(default=60.0, gt=0, le=3600)

    @field_validator("require_approval_before_merge")
    @classmethod
    def _approval_required(cls, value: bool) -> bool:
        if not value:
            raise ValueError(
                "require_approval_before_merge cannot be disabled in this release: "
                "AgentBridge never merges agent changes without human approval"
            )
        return value


class ProviderSettings(_Strict):
    """Settings for one provider entry. Unused fields are ignored per adapter type."""

    enabled: bool = True
    type: str | None = None
    execution_mode: Literal["cli", "remote_handoff", "simulated"] | None = None
    command: str | None = None
    model: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=86_400)
    # claude_code
    permission_mode: Literal["plan", "acceptEdits", "default", "dontAsk"] | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    extra_args: list[str] = Field(default_factory=list)
    # antigravity_remote
    git_remote: str = "origin"
    # generic_cli: argument template; "{prompt_file}" and "{workdir}" are substituted
    args: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    # mock
    scenario: Literal[
        "success", "failure", "delay", "interrupt", "invalid_output", "unavailable"
    ] = "success"
    delay_seconds: float = Field(default=0.0, ge=0, le=3600)
    files: dict[str, str] = Field(default_factory=dict)

    @field_validator("extra_args")
    @classmethod
    def _no_permission_bypass(cls, value: list[str]) -> list[str]:
        forbidden = {"--dangerously-skip-permissions", "bypassPermissions"}
        if forbidden.intersection(value):
            raise ValueError("extra_args may not disable provider permission checks")
        return value


class RoutingSettings(_Strict):
    planner: str = "mock"
    default_worker: str = "mock"
    reviewer: str | None = None
    roles: dict[str, str] = Field(default_factory=dict)


class WorkspaceSettings(_Strict):
    use_git_worktree: bool = True
    worktree_directory: str = f"{STATE_DIRNAME}/worktrees"
    branch_prefix: str = "agentbridge"

    @field_validator("branch_prefix")
    @classmethod
    def _valid_prefix(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,30}", value):
            raise ValueError("branch_prefix must be lowercase alphanumeric/dash/underscore")
        return value


class ValidationSettings(_Strict):
    run_tests: bool = True
    run_lint: bool = True
    run_type_check: bool = True
    # "{python}" resolves to the interpreter running AgentBridge.
    test_command: list[str] = Field(default_factory=lambda: ["{python}", "-m", "pytest", "-q"])
    lint_command: list[str] = Field(
        default_factory=lambda: ["{python}", "-m", "ruff", "check", "."]
    )
    type_check_command: list[str] = Field(
        default_factory=lambda: ["{python}", "-m", "mypy", "--ignore-missing-imports", "."]
    )
    type_check_blocking: bool = False
    lint_blocking: bool = True
    command_timeout_seconds: int = Field(default=600, ge=1, le=7200)
    max_changed_files: int = Field(default=200, ge=1)


class SecuritySettings(_Strict):
    policy: PolicyProfile = PolicyProfile.STANDARD
    require_approval_for_merge: bool = True
    allow_force_push: bool = False
    allow_destructive_commands: bool = False
    extra_allowed_commands: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _protected_operations(self) -> SecuritySettings:
        if self.allow_force_push:
            raise ValueError("allow_force_push must be false: force-push is never permitted")
        if self.allow_destructive_commands:
            raise ValueError(
                "allow_destructive_commands must be false: destructive commands are not "
                "supported in this release"
            )
        if not self.require_approval_for_merge:
            raise ValueError("require_approval_for_merge cannot be disabled")
        return self


class Settings(_Strict):
    version: Literal[1] = 1
    project: ProjectSettings = Field(default_factory=ProjectSettings)
    orchestration: OrchestrationSettings = Field(default_factory=OrchestrationSettings)
    providers: dict[str, ProviderSettings] = Field(
        default_factory=lambda: {"mock": ProviderSettings(type="mock")}
    )
    routing: RoutingSettings = Field(default_factory=RoutingSettings)
    workspace: WorkspaceSettings = Field(default_factory=WorkspaceSettings)
    validation: ValidationSettings = Field(default_factory=ValidationSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    @model_validator(mode="after")
    def _check_providers(self) -> Settings:
        for name, provider in self.providers.items():
            if not _PROVIDER_NAME.match(name):
                raise ValueError(
                    f"invalid provider name {name!r}: use lowercase letters, digits, - or _"
                )
            if provider.type is None:
                inferred = _DEFAULT_TYPE_BY_NAME.get(name)
                if inferred is None:
                    raise ValueError(
                        f"provider {name!r} needs an explicit 'type' "
                        f"(one of {', '.join(KNOWN_PROVIDER_TYPES)})"
                    )
                provider.type = inferred
            if provider.type not in KNOWN_PROVIDER_TYPES:
                raise ValueError(
                    f"provider {name!r} has unknown type {provider.type!r} "
                    f"(expected one of {', '.join(KNOWN_PROVIDER_TYPES)})"
                )
            if provider.type == "generic_cli" and not provider.command:
                raise ValueError(f"generic_cli provider {name!r} requires 'command'")
        referenced = {
            "routing.planner": self.routing.planner,
            "routing.default_worker": self.routing.default_worker,
        }
        if self.routing.reviewer:
            referenced["routing.reviewer"] = self.routing.reviewer
        for role, provider_name in self.routing.roles.items():
            referenced[f"routing.roles.{role}"] = provider_name
        for field_name, provider_name in referenced.items():
            if provider_name not in self.providers:
                raise ValueError(
                    f"{field_name} refers to provider {provider_name!r}, which is not "
                    "defined under 'providers'"
                )
        return self

    def provider(self, name: str) -> ProviderSettings:
        return self.providers[name]


def default_config_dict(project_name: str, default_branch: str = "main") -> dict[str, Any]:
    """The configuration written by ``agentbridge init``.

    Claude Code is configured but routing starts on the mock provider so a new
    project works without external accounts; switch ``routing`` to ``claude`` once
    ``agentbridge providers check`` reports it as available.
    """
    return {
        "version": 1,
        "project": {
            "name": project_name,
            "repository": ".",
            "default_branch": default_branch,
        },
        "orchestration": {
            "max_parallel_tasks": 2,
            "retry_limit": 2,
            "task_timeout_seconds": 1800,
            "require_approval_before_merge": True,
            "planner_mode": "single",
        },
        "providers": {
            "claude": {
                "enabled": True,
                "execution_mode": "cli",
                "command": "claude",
                "permission_mode": "acceptEdits",
            },
            "antigravity": {
                "enabled": False,
                "execution_mode": "remote_handoff",
                "command": "agy",
                "git_remote": "origin",
            },
            "mock": {"enabled": True, "scenario": "success"},
        },
        "routing": {
            "planner": "mock",
            "default_worker": "mock",
            "reviewer": None,
        },
        "workspace": {
            "use_git_worktree": True,
            "worktree_directory": f"{STATE_DIRNAME}/worktrees",
        },
        "validation": {
            "run_tests": True,
            "run_lint": True,
            "run_type_check": True,
        },
        "security": {
            "policy": "standard",
            "require_approval_for_merge": True,
            "allow_force_push": False,
            "allow_destructive_commands": False,
        },
    }
