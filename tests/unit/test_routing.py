import asyncio

import pytest

from agentbridge.agents.capabilities import Capability
from agentbridge.agents.registry import AgentRegistry
from agentbridge.config.settings import PolicyProfile, ProviderSettings, RoutingSettings, Settings
from agentbridge.core.router import Router
from agentbridge.errors import PolicyViolationError, ProviderUnavailableError
from agentbridge.security.policies import build_policy
from agentbridge.tasks.models import ROLE_CAPABILITIES, TaskRole


def make(providers, routing, policy=PolicyProfile.STANDARD):
    settings = Settings(providers=providers, routing=routing)
    registry = AgentRegistry(settings)
    return Router(settings, registry, build_policy(policy)), registry


def route(router, role, preferred=None):
    return asyncio.run(router.route(role, ROLE_CAPABILITIES[role], preferred))


def test_registry_builds_known_adapters():
    _, registry = make(
        {
            "mock": ProviderSettings(type="mock"),
            "claude": ProviderSettings(),
            "antigravity": ProviderSettings(enabled=False),
        },
        RoutingSettings(),
    )
    assert set(registry.names()) == {"mock", "claude", "antigravity"}
    assert registry.get("claude").provider_type == "claude_code"
    with pytest.raises(ProviderUnavailableError, match="disabled"):
        registry.get("antigravity")


def test_role_mapping_and_explanation():
    router, _ = make(
        {"mock": ProviderSettings(type="mock"), "other": ProviderSettings(type="mock")},
        RoutingSettings(default_worker="mock", roles={"reviewer": "other"}),
    )
    decision = route(router, TaskRole.REVIEWER)
    assert decision.provider == "other"
    assert "routing.roles.reviewer" in decision.explain()


def test_incompatible_provider_is_skipped():
    # The remote handoff provider does not declare 'review'.
    router, _ = make(
        {"mock": ProviderSettings(type="mock"), "antigravity": ProviderSettings()},
        RoutingSettings(default_worker="mock", roles={"reviewer": "antigravity"}),
    )
    decision = route(router, TaskRole.REVIEWER)
    assert decision.provider == "mock"
    assert "missing capabilities: review" in decision.rejected["antigravity"]


def test_unavailable_provider_is_skipped_and_reported():
    router, _ = make(
        {"down": ProviderSettings(type="mock", scenario="unavailable")},
        RoutingSettings(planner="down", default_worker="down"),
    )
    with pytest.raises(ProviderUnavailableError, match="unavailable"):
        route(router, TaskRole.DEVELOPER)


def test_explicit_provider_must_be_compatible():
    router, _ = make(
        {"mock": ProviderSettings(type="mock"), "antigravity": ProviderSettings()},
        RoutingSettings(),
    )
    with pytest.raises(ProviderUnavailableError, match="missing capabilities"):
        route(router, TaskRole.REVIEWER, preferred="antigravity")


def test_safe_policy_blocks_editing_roles():
    router, _ = make({"mock": ProviderSettings(type="mock")}, RoutingSettings(), PolicyProfile.SAFE)
    with pytest.raises(PolicyViolationError):
        route(router, TaskRole.DEVELOPER)
    assert route(router, TaskRole.ANALYST).provider == "mock"


def test_capabilities_are_declared_not_assumed():
    _, registry = make(
        {"mock": ProviderSettings(type="mock"), "antigravity": ProviderSettings()},
        RoutingSettings(),
    )
    remote = asyncio.run(registry.get("antigravity").get_capabilities())
    assert Capability.HUMAN_IN_THE_LOOP in remote.capabilities
    assert Capability.LOCAL_WORKSPACE not in remote.capabilities
    assert remote.execution.value == "manual"
