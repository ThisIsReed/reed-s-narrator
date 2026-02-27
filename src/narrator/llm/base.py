"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from .schemas import HealthCheckResponse, StructuredResponse

T = TypeVar("T", bound=StructuredResponse)


@dataclass(frozen=True)
class LLMRequest:
    """Request payload for LLM calls."""

    system_prompt: str = field(default="")
    user_prompt: str = field(default="")
    temperature: float = field(default=0.7)
    max_tokens: int = field(default=1024)
    top_p: float = field(default=1.0)


@dataclass(frozen=True)
class LLMResponse:
    """Response from an LLM call."""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    raw_response: Any = field(default=None)


class ProviderError(Exception):
    """Base exception for provider errors."""


class ProviderUnavailableError(ProviderError):
    """Raised when the provider is unavailable."""


class ProviderValidationError(ProviderError):
    """Raised when response validation fails."""


class LLMProvider(ABC, Generic[T]):
    """Abstract base class for LLM providers.

    All provider implementations must inherit from this class and
    implement the abstract methods.
    """

    def __init__(self, model: str, **kwargs: Any) -> None:
        """Initialize the provider.

        Args:
            model: The model identifier to use
            **kwargs: Additional provider-specific configuration
        """
        self._model = model
        self._config = kwargs

    @property
    def model(self) -> str:
        """Return the current model identifier."""
        return self._model

    @property
    def provider_name(self) -> str:
        """Return the provider name for logging."""
        return self.__class__.__name__

    @abstractmethod
    async def health_check(self) -> HealthCheckResponse:
        """Check if the provider is healthy and available.

        Returns:
            HealthCheckResponse with status information
        """
        pass

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Perform a standard completion request.

        Args:
            request: The completion request payload

        Returns:
            LLMResponse with the generated content
        """
        pass

    @abstractmethod
    async def complete_structured(
        self, request: LLMRequest, response_type: type[T]
    ) -> T:
        """Perform a completion request with structured output.

        Args:
            request: The completion request payload
            response_type: The expected response schema type

        Returns:
            Validated structured response object

        Raises:
            ProviderValidationError: If the response fails validation
            ProviderError: If the provider encounters an error
        """
        pass

    def _validate_response(
        self, response_data: dict[str, Any], response_type: type[T]
    ) -> T:
        """Validate a response against the expected schema.

        Args:
            response_data: The raw response data
            response_type: The expected schema type

        Returns:
            Validated structured response

        Raises:
            ProviderValidationError: If validation fails
        """
        from .schemas import validate_structured_response

        is_valid, validated, error_msg = validate_structured_response(
            response_data, response_type
        )
        if not is_valid or validated is None:
            raise ProviderValidationError(error_msg)
        return validated
