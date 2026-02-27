from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from narrator.config import ConfigLoadError, load_config


def _write_config(path: Path, content: str) -> Path:
    config_path = path / "config.yaml"
    config_path.write_text(content, encoding="utf-8")
    return config_path


def test_load_config_with_env_substitution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    config_path = _write_config(
        tmp_path,
        """
simulation: {tick_unit_hours: 1, max_ticks: 10000, checkpoint_interval: 100}
narrator: {max_retry: 3, instant_mode_max_rounds: 3}
spotlight:
  weights: {geo: 0.3, relation: 0.2, availability: 0.15, narrative_importance: 0.25, random_noise: 0.1}
  threshold_active: 0.7
  threshold_passive: 0.3
phenology: {enabled_effects: [winter_march_penalty]}
llm:
  default_provider: openai
  providers:
    openai: {model: gpt-4o, api_key: "${OPENAI_API_KEY}", max_tokens: 2048}
    anthropic: {model: claude-sonnet-4-20250514, api_key: "${ANTHROPIC_API_KEY}"}
    ollama: {model: llama3, base_url: http://localhost:11434}
persistence: {db_path: data/narrator.db, enable_wal: true}
""",
    )

    app_config = load_config(config_path)
    assert app_config.llm.providers.openai.api_key == "openai-secret"
    assert app_config.llm.providers.anthropic.api_key == "anthropic-secret"


def test_load_config_missing_required_field_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    config_path = _write_config(
        tmp_path,
        """
narrator: {max_retry: 3, instant_mode_max_rounds: 3}
spotlight:
  weights: {geo: 0.3, relation: 0.2, availability: 0.15, narrative_importance: 0.25, random_noise: 0.1}
  threshold_active: 0.7
  threshold_passive: 0.3
phenology: {enabled_effects: [winter_march_penalty]}
llm:
  default_provider: openai
  providers:
    openai: {model: gpt-4o, api_key: "${OPENAI_API_KEY}", max_tokens: 2048}
    anthropic: {model: claude-sonnet-4-20250514, api_key: "${ANTHROPIC_API_KEY}"}
    ollama: {model: llama3, base_url: http://localhost:11434}
persistence: {db_path: data/narrator.db, enable_wal: true}
""",
    )

    with pytest.raises(ConfigLoadError) as exc_info:
        load_config(config_path)

    assert "config validation failed" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_load_config_type_error_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    config_path = _write_config(
        tmp_path,
        """
simulation: {tick_unit_hours: 1, max_ticks: bad, checkpoint_interval: 100}
narrator: {max_retry: 3, instant_mode_max_rounds: 3}
spotlight:
  weights: {geo: 0.3, relation: 0.2, availability: 0.15, narrative_importance: 0.25, random_noise: 0.1}
  threshold_active: 0.7
  threshold_passive: 0.3
phenology: {enabled_effects: [winter_march_penalty]}
llm:
  default_provider: openai
  providers:
    openai: {model: gpt-4o, api_key: "${OPENAI_API_KEY}", max_tokens: 2048}
    anthropic: {model: claude-sonnet-4-20250514, api_key: "${ANTHROPIC_API_KEY}"}
    ollama: {model: llama3, base_url: http://localhost:11434}
persistence: {db_path: data/narrator.db, enable_wal: true}
""",
    )

    with pytest.raises(ConfigLoadError) as exc_info:
        load_config(config_path)

    assert "config validation failed" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_load_config_missing_env_var_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    config_path = _write_config(
        tmp_path,
        """
simulation: {tick_unit_hours: 1, max_ticks: 10000, checkpoint_interval: 100}
narrator: {max_retry: 3, instant_mode_max_rounds: 3}
spotlight:
  weights: {geo: 0.3, relation: 0.2, availability: 0.15, narrative_importance: 0.25, random_noise: 0.1}
  threshold_active: 0.7
  threshold_passive: 0.3
phenology: {enabled_effects: [winter_march_penalty]}
llm:
  default_provider: openai
  providers:
    openai: {model: gpt-4o, api_key: "${OPENAI_API_KEY}", max_tokens: 2048}
    anthropic: {model: claude-sonnet-4-20250514, api_key: "${ANTHROPIC_API_KEY}"}
    ollama: {model: llama3, base_url: http://localhost:11434}
persistence: {db_path: data/narrator.db, enable_wal: true}
""",
    )

    with pytest.raises(ConfigLoadError) as exc_info:
        load_config(config_path)

    assert "missing environment variable: OPENAI_API_KEY" in str(exc_info.value)
