"""Configuration loading and validation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


class ConfigLoadError(RuntimeError):
    """Raised when application config cannot be loaded."""


class StrictModel(BaseModel):
    """Immutable strict config model."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SimulationConfig(StrictModel):
    tick_unit_hours: int = Field(..., gt=0)
    max_ticks: int = Field(..., gt=0)
    checkpoint_interval: int = Field(..., gt=0)


class NarratorConfig(StrictModel):
    max_retry: int = Field(..., ge=0)
    instant_mode_max_rounds: int = Field(..., gt=0)


class SpotlightWeights(StrictModel):
    geo: float = Field(..., ge=0.0, le=1.0)
    relation: float = Field(..., ge=0.0, le=1.0)
    availability: float = Field(..., ge=0.0, le=1.0)
    narrative_importance: float = Field(..., ge=0.0, le=1.0)
    random_noise: float = Field(..., ge=0.0, le=1.0)


class SpotlightConfig(StrictModel):
    weights: SpotlightWeights
    threshold_active: float = Field(..., ge=0.0, le=1.0)
    threshold_passive: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "SpotlightConfig":
        if self.threshold_active <= self.threshold_passive:
            raise ValueError("threshold_active must be greater than threshold_passive")
        return self


class PhenologyConfig(StrictModel):
    enabled_effects: list[str] = Field(..., min_length=1)


class OpenAIProviderConfig(StrictModel):
    model: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    max_tokens: int = Field(..., gt=0)


class AnthropicProviderConfig(StrictModel):
    model: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)


class OllamaProviderConfig(StrictModel):
    model: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)


class LLMProvidersConfig(StrictModel):
    openai: OpenAIProviderConfig
    anthropic: AnthropicProviderConfig
    ollama: OllamaProviderConfig


class LLMConfig(StrictModel):
    default_provider: Literal["openai", "anthropic", "ollama"]
    providers: LLMProvidersConfig


class PersistenceConfig(StrictModel):
    db_path: str = Field(..., min_length=1)
    enable_wal: bool


class AppConfig(StrictModel):
    simulation: SimulationConfig
    narrator: NarratorConfig
    spotlight: SpotlightConfig
    phenology: PhenologyConfig
    llm: LLMConfig
    persistence: PersistenceConfig


def _replace_env_tokens(value: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        env_name = match.group(1)
        env_value = os.getenv(env_name)
        if env_value is None:
            raise ConfigLoadError(f"missing environment variable: {env_name}")
        return env_value

    return ENV_PATTERN.sub(replacement, value)


def _resolve_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(item) for item in value]
    if isinstance(value, str):
        return _replace_env_tokens(value)
    return value


def load_config(path: str | Path = "config/default.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigLoadError(f"config file not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"invalid yaml format: {config_path}") from exc

    if raw is None:
        raise ConfigLoadError(f"empty config file: {config_path}")
    if not isinstance(raw, dict):
        raise ConfigLoadError("config root must be a mapping")

    resolved = _resolve_env(raw)
    try:
        return AppConfig.model_validate(resolved)
    except ValidationError as exc:
        raise ConfigLoadError("config validation failed") from exc
