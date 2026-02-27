"""LLM provider abstraction layer."""

from .anthropic import AnthropicProvider
from .base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
    ProviderUnavailableError,
    ProviderValidationError,
)
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .router import LLMRouter, ProviderNotConfiguredError, RouterError
from .schemas import (
    DecisionResponse,
    HealthCheckResponse,
    IntentResponse,
    StructuredResponse,
    validate_structured_response,
)

__all__ = [
    # Base
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "ProviderError",
    "ProviderUnavailableError",
    "ProviderValidationError",
    # Providers
    "OpenAIProvider",
    "AnthropicProvider",
    "OllamaProvider",
    # Router
    "LLMRouter",
    "ProviderNotConfiguredError",
    "RouterError",
    # Schemas
    "StructuredResponse",
    "IntentResponse",
    "DecisionResponse",
    "HealthCheckResponse",
    "validate_structured_response",
]
