"""Structured output schemas for LLM responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class StructuredResponse(BaseModel):
    """Base schema for structured LLM responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(..., description="The main content of the response")


class IntentResponse(BaseModel):
    """Schema for character intent generation responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: str = Field(..., description="The action intent name")
    flavor_text: str = Field(..., description="Narrative flavor text")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Action parameters"
    )


class DecisionResponse(BaseModel):
    """Schema for DM agent decision responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: str = Field(..., description="Decision verdict (ACCEPT/REJECT)")
    reason: str = Field(..., description="Reason for the decision")
    outcome: dict[str, Any] = Field(
        default_factory=dict, description="Decision outcome data"
    )


class HealthCheckResponse(BaseModel):
    """Schema for LLM provider health check responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    healthy: bool = Field(..., description="Whether the provider is healthy")
    message: str = Field(default="", description="Optional status message")


def validate_structured_response(
    response_data: dict[str, Any], response_type: type[BaseModel]
) -> tuple[bool, BaseModel | None, str]:
    """Validate a structured response against the expected schema.

    Args:
        response_data: The raw response data to validate
        response_type: The expected response schema type

    Returns:
        A tuple of (is_valid, validated_model_or_none, error_message)
    """
    try:
        validated = response_type.model_validate(response_data)
        return True, validated, ""
    except ValidationError as e:
        return False, None, f"validation failed: {e}"
    except Exception as e:
        return False, None, f"unexpected error: {e}"
