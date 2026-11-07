from pathlib import Path

import pytest
import yaml

from agentbridge.config.loader import load_project, load_settings, parse_settings, write_config
from agentbridge.config.settings import Settings, default_config_dict
from agentbridge.errors import ConfigError


def test_defaults_are_valid():
    settings = Settings()
    assert settings.security.policy.value == "standard"
    assert settings.orchestration.require_approval_before_merge is True


def test_init_config_round_trip(tmp_path: Path):
    path = tmp_path / "agentbridge.yaml"
    write_config(path, default_config_dict("demo"))
    settings = load_settings(path)
    assert settings.project.name == "demo"
    assert settings.providers["claude"].type == "claude_code"
    assert settings.providers["antigravity"].type == "antigravity_remote"
    assert settings.providers["antigravity"].enabled is False


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"security": {"allow_force_push": True}}, "force"),
        ({"security": {"allow_destructive_commands": True}}, "destructive"),
        ({"orchestration": {"require_approval_before_merge": False}}, "approval"),
        ({"orchestration": {"max_parallel_tasks": 0}}, "max_parallel_tasks"),
        ({"providers": {"weird": {}}}, "explicit 'type'"),
        ({"providers": {"x": {"type": "nope"}}}, "unknown type"),
        ({"routing": {"default_worker": "ghost"}}, "ghost"),
        (
            {"providers": {"claude": {"extra_args": ["--dangerously-skip-permissions"]}}},
            "permission",
        ),
        ({"unknown_section": {}}, "unknown_section"),
        ({"version": 2}, "version"),
    ],
)
def test_invalid_config_rejected(patch, message):
    data = default_config_dict("demo")
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    with pytest.raises(ConfigError, match=message):
        parse_settings(data)


def test_actionable_errors(tmp_path: Path):
    with pytest.raises(ConfigError) as info:
        load_settings(tmp_path / "missing.yaml")
    assert "agentbridge init" in (info.value.hint or "")
    bad = tmp_path / "agentbridge.yaml"
    bad.write_text("version: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_settings(bad)


def test_load_project_walks_up(tmp_path: Path):
    write_config(tmp_path / "agentbridge.yaml", default_config_dict("demo"))
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    paths, _ = load_project(nested)
    assert paths.root == tmp_path.resolve()


def test_written_config_has_no_credentials(tmp_path: Path):
    path = tmp_path / "agentbridge.yaml"
    write_config(path, default_config_dict("demo"))
    text = path.read_text(encoding="utf-8").lower()
    data = yaml.safe_load(text)
    assert "api_key" not in text and "token" not in text
    assert data["security"]["allow_force_push"] is False
