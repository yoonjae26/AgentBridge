"""Explainable provider routing based on declared capabilities and policy."""

from __future__ import annotations

from dataclasses import dataclass, field

from agentbridge.agents.base import AvailabilityReport
from agentbridge.agents.capabilities import Capability
from agentbridge.agents.registry import AgentRegistry
from agentbridge.config.settings import Settings
from agentbridge.errors import PolicyViolationError, ProviderUnavailableError
from agentbridge.security.policies import Policy
from agentbridge.tasks.models import EDITING_ROLES, TaskRole


@dataclass
class RoutingDecision:
    provider: str
    reason: str
    rejected: dict[str, str] = field(default_factory=dict)

    def explain(self) -> str:
        parts = [f"selected '{self.provider}': {self.reason}"]
        parts += [f"skipped '{name}': {why}" for name, why in self.rejected.items()]
        return "; ".join(parts)


class Router:
    def __init__(self, settings: Settings, registry: AgentRegistry, policy: Policy) -> None:
        self.settings = settings
        self.registry = registry
        self.policy = policy
        self._availability: dict[str, AvailabilityReport] = {}

    async def availability(self, name: str) -> AvailabilityReport:
        if name not in self._availability:
            adapter = self.registry.get(name, require_enabled=False)
            self._availability[name] = await adapter.check_availability()
        return self._availability[name]

    def _candidates(self, role: TaskRole, preferred: str | None) -> list[tuple[str, str]]:
        routing = self.settings.routing
        ordered: list[tuple[str, str]] = []
        if preferred:
            return [(preferred, "requested explicitly")]
        if role.value in routing.roles:
            ordered.append((routing.roles[role.value], f"routing.roles.{role.value}"))
        if role is TaskRole.PLANNER:
            ordered.append((routing.planner, "routing.planner"))
        if role is TaskRole.REVIEWER and routing.reviewer:
            ordered.append((routing.reviewer, "routing.reviewer"))
        ordered.append((routing.default_worker, "routing.default_worker"))
        seen: set[str] = set()
        unique = []
        for name, why in ordered:
            if name not in seen:
                unique.append((name, why))
                seen.add(name)
        return unique

    async def route(
        self,
        role: TaskRole,
        required: frozenset[Capability],
        preferred: str | None = None,
    ) -> RoutingDecision:
        if role in EDITING_ROLES and not self.policy.agents_may_edit:
            raise PolicyViolationError(
                f"The '{self.policy.profile.value}' policy permits read-only analysis only; "
                f"a {role.value} task cannot run",
                hint="Use --policy standard, or set security.policy in agentbridge.yaml.",
            )
        rejected: dict[str, str] = {}
        for name, why in self._candidates(role, preferred):
            if name not in self.registry.names():
                rejected[name] = "not configured"
                continue
            if not self.registry.is_enabled(name):
                rejected[name] = "disabled in configuration"
                continue
            adapter = self.registry.get(name)
            capabilities = await adapter.get_capabilities()
            missing = capabilities.missing(set(required))
            if missing:
                rejected[name] = "missing capabilities: " + ", ".join(
                    sorted(m.value for m in missing)
                )
                continue
            report = await self.availability(name)
            if not report.available:
                rejected[name] = "unavailable: " + "; ".join(report.details[:2])
                continue
            return RoutingDecision(
                provider=name,
                reason=f"{why}; declares {', '.join(sorted(c.value for c in required))}",
                rejected=rejected,
            )
        details = "; ".join(f"{n}: {w}" for n, w in rejected.items()) or "no candidates"
        raise ProviderUnavailableError(
            f"No compatible provider for a {role.value} task ({details})",
            hint="Run 'agentbridge providers check' and review the routing section.",
        )
