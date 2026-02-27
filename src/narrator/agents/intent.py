"""Intent protocol and action whitelist validator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, ValidationError, model_validator

from narrator.models.base import DomainModel


class IntentValidationError(RuntimeError):
    """Raised when intent payload or whitelist is invalid."""


class ActionRule(DomainModel):
    required_params: tuple[str, ...] = ()
    optional_params: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_param_overlap(self) -> "ActionRule":
        overlap = set(self.required_params) & set(self.optional_params)
        if overlap:
            dup = ",".join(sorted(overlap))
            raise ValueError(f"duplicated params in rule: {dup}")
        return self


class ActionWhitelist(DomainModel):
    version: int = Field(..., ge=1)
    actions: dict[str, ActionRule] = Field(..., min_length=1)


class IntentPayload(DomainModel):
    character_id: str = Field(..., min_length=1)
    action_type: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    target_id: str | None = None
    flavor_text: str = Field(..., min_length=1)


def load_action_whitelist(path: str | Path = "config/schemas/action_whitelist.yaml") -> ActionWhitelist:
    file_path = Path(path)
    if not file_path.exists():
        raise IntentValidationError(f"action whitelist file not found: {file_path}")
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise IntentValidationError(f"invalid action whitelist yaml: {file_path}") from exc
    try:
        return ActionWhitelist.model_validate(raw)
    except ValidationError as exc:
        raise IntentValidationError("action whitelist validation failed") from exc


def validate_intent(payload: IntentPayload | dict[str, Any], whitelist: ActionWhitelist) -> IntentPayload:
    intent = _parse_intent(payload)
    rule = whitelist.actions.get(intent.action_type)
    if rule is None:
        raise IntentValidationError(f"action not allowed: {intent.action_type}")
    _validate_parameters(intent.parameters, rule)
    return intent


def _parse_intent(payload: IntentPayload | dict[str, Any]) -> IntentPayload:
    if isinstance(payload, IntentPayload):
        return payload
    try:
        return IntentPayload.model_validate(payload)
    except ValidationError as exc:
        raise IntentValidationError("intent payload validation failed") from exc


def _validate_parameters(parameters: dict[str, Any], rule: ActionRule) -> None:
    keys = set(parameters.keys())
    required = set(rule.required_params)
    optional = set(rule.optional_params)
    allowed = required | optional
    missing = required - keys
    unknown = keys - allowed
    if missing:
        names = ",".join(sorted(missing))
        raise IntentValidationError(f"missing required parameters: {names}")
    if unknown:
        names = ",".join(sorted(unknown))
        raise IntentValidationError(f"unknown parameters: {names}")
