"""Builds adapter instances from configuration."""

from __future__ import annotations

from agentbridge.agents.antigravity.adapter import AntigravityRemoteAdapter
from agentbridge.agents.base import AgentAdapter
from agentbridge.agents.claude.adapter import ClaudeCodeAdapter
from agentbridge.agents.generic_cli.adapter import GenericCliAdapter
from agentbridge.agents.mock.adapter import MockAdapter
from agentbridge.config.settings import Settings
from agentbridge.errors import ConfigError, ProviderUnavailableError

ADAPTER_TYPES: dict[str, type[AgentAdapter]] = {
    "mock": MockAdapter,
    "claude_code": ClaudeCodeAdapter,
    "antigravity_remote": AntigravityRemoteAdapter,
    "generic_cli": GenericCliAdapter,
}


class AgentRegistry:
    def __init__(self, settings: Settings) -> None:
        self._adapters: dict[str, AgentAdapter] = {}
        self._enabled: dict[str, bool] = {}
        for name, provider in settings.providers.items():
            adapter_type = ADAPTER_TYPES.get(provider.type or "")
            if adapter_type is None:
                raise ConfigError(f"Unknown provider type for {name!r}: {provider.type}")
            self._adapters[name] = adapter_type(name, provider)
            self._enabled[name] = provider.enabled

    def names(self) -> list[str]:
        return list(self._adapters)

    def is_enabled(self, name: str) -> bool:
        return self._enabled.get(name, False)

    def enabled(self) -> list[AgentAdapter]:
        return [a for n, a in self._adapters.items() if self._enabled[n]]

    def get(self, name: str, *, require_enabled: bool = True) -> AgentAdapter:
        adapter = self._adapters.get(name)
        if adapter is None:
            raise ProviderUnavailableError(
                f"Unknown provider: {name}",
                hint=f"Configured providers: {', '.join(self._adapters) or 'none'}",
            )
        if require_enabled and not self._enabled[name]:
            raise ProviderUnavailableError(
                f"Provider '{name}' is disabled",
                hint=f"Set providers.{name}.enabled: true in agentbridge.yaml",
            )
        return adapter

    def register(self, adapter: AgentAdapter, enabled: bool = True) -> None:
        """Register an adapter instance directly (used by tests and extensions)."""
        self._adapters[adapter.name] = adapter
        self._enabled[adapter.name] = enabled
