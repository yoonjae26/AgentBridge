"""Error types and the stable exit-code contract used by the CLI."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Predictable process exit codes for automation.

    These values are part of the public CLI contract; do not renumber them.
    """

    OK = 0
    TASK_FAILED = 1
    CONFIG_ERROR = 2
    PROVIDER_UNAVAILABLE = 3
    VALIDATION_FAILED = 4
    NOT_FOUND = 5
    POLICY_VIOLATION = 6
    INVALID_STATE = 7
    GIT_ERROR = 8
    CANCELLED = 130


class AgentBridgeError(Exception):
    """Base class for all expected, user-facing errors."""

    exit_code: ExitCode = ExitCode.TASK_FAILED

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class ConfigError(AgentBridgeError):
    exit_code = ExitCode.CONFIG_ERROR


class ProviderUnavailableError(AgentBridgeError):
    exit_code = ExitCode.PROVIDER_UNAVAILABLE


class NotFoundError(AgentBridgeError):
    exit_code = ExitCode.NOT_FOUND


class PolicyViolationError(AgentBridgeError):
    exit_code = ExitCode.POLICY_VIOLATION


class InvalidTransitionError(AgentBridgeError):
    exit_code = ExitCode.INVALID_STATE


class InvalidStateError(AgentBridgeError):
    exit_code = ExitCode.INVALID_STATE


class GitError(AgentBridgeError):
    exit_code = ExitCode.GIT_ERROR


class PlanValidationError(AgentBridgeError):
    exit_code = ExitCode.TASK_FAILED
