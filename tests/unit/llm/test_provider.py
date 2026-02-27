"""Unit tests for LLM provider abstraction (WP-06)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from narrator.llm.base import (
    LLMRequest,
    LLMResponse,
    ProviderError,
    ProviderValidationError,
)
from narrator.llm.schemas import (
    DecisionResponse,
    HealthCheckResponse,
    IntentResponse,
    StructuredResponse,
    validate_structured_response,
)


# --- Schema Tests ---

def test_structured_response_valid() -> None:
    """Test valid StructuredResponse creation."""
    response = StructuredResponse(content="Test content")
    assert response.content == "Test content"


def test_structured_response_extra_field_rejected() -> None:
    """Test that extra fields are rejected."""
    with pytest.raises(ValidationError):
        StructuredResponse(
            content="Test",
            extra_field="should fail",
        )


def test_structured_response_frozen() -> None:
    """Test that StructuredResponse is frozen."""
    response = StructuredResponse(content="Test")
    with pytest.raises(ValidationError):
        response.content = "Modified"


def test_intent_response_valid() -> None:
    """Test valid IntentResponse creation."""
    response = IntentResponse(
        intent="move",
        flavor_text="The character moves forward",
        parameters={"target": "north"},
    )
    assert response.intent == "move"
    assert response.flavor_text == "The character moves forward"
    assert response.parameters == {"target": "north"}


def test_intent_response_minimal() -> None:
    """Test IntentResponse with minimal parameters."""
    response = IntentResponse(
        intent="rest",
        flavor_text="Resting...",
    )
    assert response.intent == "rest"
    assert response.parameters == {}


def test_decision_response_valid() -> None:
    """Test valid DecisionResponse creation."""
    response = DecisionResponse(
        verdict="ACCEPT",
        reason="Action is valid",
        outcome={"success": True},
    )
    assert response.verdict == "ACCEPT"
    assert response.reason == "Action is valid"
    assert response.outcome == {"success": True}


def test_health_check_response_valid() -> None:
    """Test valid HealthCheckResponse creation."""
    response = HealthCheckResponse(healthy=True, message="OK")
    assert response.healthy is True
    assert response.message == "OK"


def test_health_check_response_default_message() -> None:
    """Test HealthCheckResponse with default message."""
    response = HealthCheckResponse(healthy=True)
    assert response.healthy is True
    assert response.message == ""


# --- Validation Tests ---

def test_validate_structured_response_success() -> None:
    """Test successful validation."""
    data = {"content": "Test"}
    is_valid, validated, error_msg = validate_structured_response(
        data, StructuredResponse
    )
    assert is_valid is True
    assert validated is not None
    assert validated.content == "Test"
    assert error_msg == ""


def test_validate_structured_response_missing_field() -> None:
    """Test validation with missing required field."""
    data = {}
    is_valid, validated, error_msg = validate_structured_response(
        data, StructuredResponse
    )
    assert is_valid is False
    assert validated is None
    assert "validation failed" in error_msg


def test_validate_structured_response_wrong_type() -> None:
    """Test validation with wrong type."""
    data = {"content": 123}  # content should be string
    is_valid, validated, error_msg = validate_structured_response(
        data, StructuredResponse
    )
    assert is_valid is False
    assert validated is None


def test_validate_intent_response_success() -> None:
    """Test IntentResponse validation."""
    data = {
        "intent": "travel",
        "flavor_text": "Traveling to the city",
        "parameters": {"destination": "city"},
    }
    is_valid, validated, error_msg = validate_structured_response(
        data, IntentResponse
    )
    assert is_valid is True
    assert validated is not None
    assert validated.intent == "travel"


def test_validate_decision_response_success() -> None:
    """Test DecisionResponse validation."""
    data = {
        "verdict": "REJECT",
        "reason": "Invalid action",
    }
    is_valid, validated, error_msg = validate_structured_response(
        data, DecisionResponse
    )
    assert is_valid is True
    assert validated is not None
    assert validated.verdict == "REJECT"


# --- LLM Request/Response Tests ---

def test_llm_request_defaults() -> None:
    """Test LLMRequest default values."""
    request = LLMRequest(
        system_prompt="You are helpful",
        user_prompt="Hello",
    )
    assert request.system_prompt == "You are helpful"
    assert request.user_prompt == "Hello"
    assert request.temperature == 0.7
    assert request.max_tokens == 1024
    assert request.top_p == 1.0


def test_llm_request_custom_values() -> None:
    """Test LLMRequest with custom values."""
    request = LLMRequest(
        system_prompt="Be creative",
        user_prompt="Write a story",
        temperature=0.9,
        max_tokens=2048,
        top_p=0.95,
    )
    assert request.temperature == 0.9
    assert request.max_tokens == 2048
    assert request.top_p == 0.95


def test_llm_response_minimal() -> None:
    """Test LLMResponse with minimal values."""
    response = LLMResponse(
        content="Hello world",
        model="gpt-4",
    )
    assert response.content == "Hello world"
    assert response.model == "gpt-4"
    assert response.usage == {}
    assert response.raw_response is None


def test_llm_response_with_usage() -> None:
    """Test LLMResponse with token usage."""
    response = LLMResponse(
        content="Response text",
        model="claude-3",
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    )
    assert response.usage["prompt_tokens"] == 10
    assert response.usage["completion_tokens"] == 20
    assert response.usage["total_tokens"] == 30


# --- Provider Base Tests ---

def test_provider_validation_error() -> None:
    """Test ProviderValidationError creation."""
    error = ProviderValidationError("Schema validation failed")
    assert str(error) == "Schema validation failed"


def test_provider_error_base() -> None:
    """Test base ProviderError."""
    error = ProviderError("Something went wrong")
    assert str(error) == "Something went wrong"
