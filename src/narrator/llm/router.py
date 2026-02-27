"""LLM Provider Router for switching between providers."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from .anthropic import AnthropicProvider
from .base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
)
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .schemas import HealthCheckResponse, StructuredResponse

T = TypeVar("T", bound=StructuredResponse)


class RouterError(ProviderError):
    """Raised when there's an error with provider routing."""


class ProviderNotConfiguredError(RouterError):
    """Raised when a requested provider is not configured."""


class LLMRouter(Generic[T]):
    """Router for managing and switching between LLM providers."""

    def __init__(self, default_provider_name: str = "openai") -> None:
        """Initialize the LLM router.

        Args:
            default_provider_name: The default provider to use
        """
        self._providers: dict[str, LLMProvider[T]] = {}
        self._default_provider_name = default_provider_name

    def register_provider(
        self, name: str, provider: LLMProvider[T], config: dict[str, Any]
    ) -> None:
        """Register a provider instance.

        Args:
            name: The provider name identifier
            provider: The provider instance
            config: The provider configuration
        """
        self._providers[name] = provider

    def get_provider(self, name: str | None = None) -> LLMProvider[T]:
        """Get a provider by name.

        Args:
            name: The provider name (uses default if None)

        Returns:
            The provider instance

        Raises:
            ProviderNotConfiguredError: If the provider is not found
        """
        provider_name = name or self._default_provider_name
        if provider_name not in self._providers:
            raise ProviderNotConfiguredError(f"provider '{provider_name}' not configured")
        return self._providers[provider_name]

    def set_default_provider(self, name: str) -> None:
        """Set the default provider.

        Args:
            name: The provider name to set as default

        Raises:
            ProviderNotConfiguredError: If the provider is not registered
        """
        if name not in self._providers:
            raise ProviderNotConfiguredError(f"provider '{name}' not registered")
        self._default_provider_name = name

    @property
    def default_provider(self) -> LLMProvider[T]:
        """Get the default provider."""
        return self.get_provider()

    @property
    def available_providers(self) -> list[str]:
        """Get list of available provider names."""
        return list(self._providers.keys())

    async def health_check_all(self) -> dict[str, HealthCheckResponse]:
        """Check health of all registered providers.

        Returns:
            Dict mapping provider names to health check responses
        """
        results = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.health_check()
            except Exception as e:
                results[name] = HealthCheckResponse(
                    healthy=False, message=f"error checking health: {e}"
                )
        return results

    async def complete(self, request: LLMRequest, provider_name: str | None = None) -> LLMResponse:
        """Route a completion request to the appropriate provider.

        Args:
            request: The completion request
            provider_name: The provider to use (uses default if None)

        Returns:
            The LLM response

        Raises:
            ProviderNotConfiguredError: If the provider is not found
        """
        provider = self.get_provider(provider_name)
        return await provider.complete(request)

    async def complete_structured(
        self, request: LLMRequest, response_type: type[T], provider_name: str | None = None
    ) -> T:
        """Route a structured completion request.

        Args:
            request: The completion request
            response_type: The expected response schema type
            provider_name: The provider to use (uses default if None)

        Returns:
            The validated structured response

        Raises:
            ProviderNotConfiguredError: If the provider is not found
        """
        provider = self.get_provider(provider_name)
        return await provider.complete_structured(request, response_type)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "LLMRouter[T]":
        """Create a router from configuration dict.

        Args:
            config: Configuration dict with 'default_provider' and 'providers' keys

        Returns:
            Configured LLMRouter instance
        """
        default_provider = config.get("default_provider", "openai")
        router = cls(default_provider_name=default_provider)

        providers_config = config.get("providers", {})

        if "openai" in providers_config:
            openai_config = providers_config["openai"]
            router.register_provider(
                "openai",
                OpenAIProvider(
                    model=openai_config["model"],
                    api_key=openai_config["api_key"],
                    max_tokens=openai_config.get("max_tokens", 1024),
                ),
                openai_config,
            )

        if "anthropic" in providers_config:
            anthropic_config = providers_config["anthropic"]
            router.register_provider(
                "anthropic",
                AnthropicProvider(
                    model=anthropic_config["model"],
                    api_key=anthropic_config["api_key"],
                    max_tokens=anthropic_config.get("max_tokens", 1024),
                ),
                anthropic_config,
            )

        if "ollama" in providers_config:
            ollama_config = providers_config["ollama"]
            router.register_provider(
                "ollama",
                OllamaProvider(
                    model=ollama_config["model"],
                    base_url=ollama_config.get("base_url", "http://localhost:11434"),
                    num_predict=ollama_config.get("num_predict", 1024),
                ),
                ollama_config,
            )

        return router
