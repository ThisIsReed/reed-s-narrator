"""Configuration loading and validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")
ENV_LINE_PATTERN = re.compile(r"^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$")
DEFAULT_ENV_PATH = Path(".env")


class ConfigLoadError(RuntimeError):
    """Raised when application config cannot be loaded."""


class StrictModel(BaseModel):
    """Immutable strict config model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        protected_namespaces=(),
    )


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
    model_name: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)
    max_tokens: int = Field(..., gt=0)


class AnthropicProviderConfig(StrictModel):
    model_name: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)


class OllamaProviderConfig(StrictModel):
    model_name: str = Field(..., min_length=1)
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


def _strip_quotes(value: str) -> str:
    if len(value) < 2:
        return value
    if value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_env_line(line: str, line_number: int) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    match = ENV_LINE_PATTERN.match(line)
    if match is None:
        raise ConfigLoadError(f"invalid env file line {line_number}")

    key, raw_value = match.groups()
    return key, _strip_quotes(raw_value.strip())


def load_env_file(path: str | Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        raise ConfigLoadError(f"env file not found: {env_path}")

    env_values: dict[str, str] = {}
    for line_number, line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        parsed = _parse_env_line(line, line_number)
        if parsed is None:
            continue
        key, value = parsed
        env_values[key] = value
    return env_values


def _replace_env_tokens(value: str, env_values: dict[str, str]) -> str:
    def replacement(match: re.Match[str]) -> str:
        env_name = match.group(1)
        env_value = env_values.get(env_name)
        if env_value is None:
            raise ConfigLoadError(f"missing environment variable: {env_name}")
        return env_value

    return ENV_PATTERN.sub(replacement, value)


def _resolve_env(value: Any, env_values: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {k: _resolve_env(v, env_values) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(item, env_values) for item in value]
    if isinstance(value, str):
        return _replace_env_tokens(value, env_values)
    return value


def load_config(path: str | Path = "config/default.yaml", env_path: str | Path = DEFAULT_ENV_PATH) -> AppConfig:
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

    env_values = load_env_file(env_path)
    resolved = _resolve_env(raw, env_values)
    try:
        return AppConfig.model_validate(resolved)
    except ValidationError as exc:
        raise ConfigLoadError("config validation failed") from exc
