"""Provider capability model.

Capabilities are *declared* by adapters. The router only assigns a task to a
provider that declares every capability the task requires; nothing is assumed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Capability(StrEnum):
    PLAN = "plan"  # can return a structured task plan
    EDIT_CODE = "edit_code"  # can modify files in an assigned workspace
    ANALYZE = "analyze"  # can read a repository and produce analysis text
    REVIEW = "review"  # can review a diff and report findings
    LOCAL_WORKSPACE = "local_workspace"  # operates on a local directory
    REMOTE_WORKSPACE = "remote_workspace"  # operates in a provider-managed environment
    STRUCTURED_OUTPUT = "structured_output"  # machine-readable output format
    CANCEL = "cancel"  # execution can be cancelled
    STATUS = "status"  # execution status can be queried after a restart
    COST_REPORTING = "cost_reporting"  # reports cost figures
    TOKEN_REPORTING = "token_reporting"  # reports token usage
    HUMAN_IN_THE_LOOP = "human_in_the_loop"  # requires a person to complete execution


class OperationSupport(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    EXPERIMENTAL = "experimental"
    MANUAL = "manual"  # performed by a human following generated instructions


class ProviderCapabilities(BaseModel):
    provider_type: str
    capabilities: frozenset[Capability] = Field(default_factory=frozenset)
    execution: OperationSupport = OperationSupport.SUPPORTED
    cancellation: OperationSupport = OperationSupport.UNSUPPORTED
    status_query: OperationSupport = OperationSupport.UNSUPPORTED
    notes: list[str] = Field(default_factory=list)

    def supports(self, required: set[Capability] | frozenset[Capability]) -> bool:
        return set(required).issubset(self.capabilities)

    def missing(self, required: set[Capability] | frozenset[Capability]) -> set[Capability]:
        return set(required) - set(self.capabilities)
