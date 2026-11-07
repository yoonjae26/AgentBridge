"""Locate, load, validate and write ``agentbridge.yaml``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agentbridge.config.settings import CONFIG_FILENAME, STATE_DIRNAME, Settings
from agentbridge.errors import ConfigError


@dataclass(frozen=True)
class ProjectPaths:
    """Filesystem layout of an initialised project."""

    root: Path

    @property
    def config_file(self) -> Path:
        return self.root / CONFIG_FILENAME

    @property
    def state_dir(self) -> Path:
        return self.root / STATE_DIRNAME

    @property
    def database(self) -> Path:
        return self.state_dir / "agentbridge.db"

    @property
    def logs_dir(self) -> Path:
        return self.state_dir / "logs"

    @property
    def artifacts_dir(self) -> Path:
        return self.state_dir / "artifacts"

    @property
    def reports_dir(self) -> Path:
        return self.state_dir / "reports"

    def worktrees_dir(self, settings: Settings) -> Path:
        configured = Path(settings.workspace.worktree_directory)
        path = configured if configured.is_absolute() else self.root / configured
        return path.resolve()

    def ensure(self) -> None:
        for directory in (self.state_dir, self.logs_dir, self.artifacts_dir, self.reports_dir):
            directory.mkdir(parents=True, exist_ok=True)


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` looking for ``agentbridge.yaml``."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / CONFIG_FILENAME).is_file():
            return candidate
    return None


def _format_validation_error(error: ValidationError) -> str:
    lines = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "<root>"
        lines.append(f"  - {location}: {item['msg']}")
    return "\n".join(lines)


def parse_settings(data: Any, source: str = CONFIG_FILENAME) -> Settings:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{source}: top level must be a mapping")
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(
            f"Invalid configuration in {source}:\n{_format_validation_error(exc)}",
            hint="Fix the listed fields, or run 'agentbridge init --force' to regenerate.",
        ) from exc


def load_settings(path: Path) -> Settings:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(
            f"Configuration file not found: {path}",
            hint="Run 'agentbridge init' in your repository first.",
        ) from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    return parse_settings(data, str(path))


def load_project(start: Path | None = None) -> tuple[ProjectPaths, Settings]:
    root = find_project_root(start)
    if root is None:
        raise ConfigError(
            f"No {CONFIG_FILENAME} found in {(start or Path.cwd()).resolve()} or its parents.",
            hint="Run 'agentbridge init' in your repository first.",
        )
    paths = ProjectPaths(root)
    settings = load_settings(paths.config_file)
    return paths, settings


def write_config(path: Path, data: dict[str, Any]) -> None:
    # Validate before writing so we never produce an unusable file.
    parse_settings(data, str(path))
    header = (
        "# AgentBridge configuration. Never put credentials in this file.\n"
        "# Provider authentication is handled by each provider's own CLI.\n"
    )
    path.write_text(header + yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


__all__ = [
    "STATE_DIRNAME",
    "ProjectPaths",
    "find_project_root",
    "load_project",
    "load_settings",
    "parse_settings",
    "write_config",
]
