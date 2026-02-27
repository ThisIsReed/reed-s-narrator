"""Unit tests for LLM Router."""

from __future__ import annotations

import pytest

from narrator.llm.base import LLMProvider, LLMRequest, LLMResponse, ProviderError
from narrator.llm.router import LLMRouter, ProviderNotConfiguredError, RouterError
from narrator.llm.schemas import HealthCheckResponse, IntentResponse, StructuredResponse


# Mock provider for testing
class MockProvider(LLMProvider[StructuredResponse]):
    """Mock provider for testing router functionality."""

    def __init__(self, model: str = "mock-model", **kwargs) -> None:
        super().__init__(model, **kwargs)
        self._health_healthy = True
        self._health_message = "OK"

    def set_health(self, healthy: bool, message: str = "") -> None:
        self._health_healthy = healthy
        self._health_message = message

    async def health_check(self) -> HealthCheckResponse:
        return HealthCheckResponse(
            healthy=self._health_healthy, message=self._health_message
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=f"Mock response from {self._model}",
            model=self._model,
        )

    async def complete_structured(
        self, request: LLMRequest, response_type: type[StructuredResponse]
    ) -> StructuredResponse:
        return response_type(content=f"Mock structured response from {self._model}")


# --- Router Basic Tests ---

def test_router_initialization_default() -> None:
    """Test router with default provider."""
    router = LLMRouter[StructuredResponse]()
    assert router._default_provider_name == "openai"
    assert router.available_providers == []


def test_router_initialization_custom() -> None:
    """Test router with custom default provider."""
    router = LLMRouter[StructuredResponse](default_provider_name="anthropic")
    assert router._default_provider_name == "anthropic"


def test_router_register_provider() -> None:
    """Test registering a provider."""
    router = LLMRouter[StructuredResponse]()
    provider = MockProvider()
    router.register_provider("mock", provider, {})
    assert "mock" in router.available_providers


def test_router_get_provider_by_name() -> None:
    """Test getting a provider by name."""
    router = LLMRouter[StructuredResponse]()
    provider = MockProvider()
    router.register_provider("mock", provider, {})
    retrieved = router.get_provider("mock")
    assert retrieved is provider


def test_router_get_default_provider() -> None:
    """Test getting the default provider."""
    router = LLMRouter[StructuredResponse](default_provider_name="mock")
    provider = MockProvider()
    router.register_provider("mock", provider, {})
    retrieved = router.default_provider
    assert retrieved is provider


def test_router_get_provider_not_configured() -> None:
    """Test getting a non-configured provider raises error."""
    router = LLMRouter[StructuredResponse]()
    with pytest.raises(ProviderNotConfiguredError):
        router.get_provider("nonexistent")


def test_router_set_default_provider() -> None:
    """Test setting the default provider."""
    router = LLMRouter[StructuredResponse]()
    provider1 = MockProvider("model1")
    provider2 = MockProvider("model2")
    router.register_provider("provider1", provider1, {})
    router.register_provider("provider2", provider2, {})
    router.set_default_provider("provider2")
    assert router.default_provider is provider2


def test_router_set_default_provider_not_registered() -> None:
    """Test setting non-registered default provider raises error."""
    router = LLMRouter[StructuredResponse]()
    with pytest.raises(ProviderNotConfiguredError):
        router.set_default_provider("nonexistent")


# --- Router Health Check Tests ---

@pytest.mark.asyncio
async def test_router_health_check_all() -> None:
    """Test health check for all providers."""
    router = LLMRouter[StructuredResponse]()
    provider1 = MockProvider()
    provider2 = MockProvider()
    provider1.set_health(True, "OK")
    provider2.set_health(False, "Error")
    router.register_provider("healthy", provider1, {})
    router.register_provider("unhealthy", provider2, {})

    results = await router.health_check_all()
    assert results["healthy"].healthy is True
    assert results["unhealthy"].healthy is False


# --- Router Completion Tests ---

@pytest.mark.asyncio
async def test_router_complete_default_provider() -> None:
    """Test completion using default provider."""
    router = LLMRouter[StructuredResponse](default_provider_name="mock")
    provider = MockProvider()
    router.register_provider("mock", provider, {})

    request = LLMRequest(system_prompt="test", user_prompt="hello")
    response = await router.complete(request)
    assert "Mock response" in response.content


@pytest.mark.asyncio
async def test_router_complete_specific_provider() -> None:
    """Test completion using specific provider."""
    router = LLMRouter[StructuredResponse]()
    provider1 = MockProvider("model1")
    provider2 = MockProvider("model2")
    router.register_provider("provider1", provider1, {})
    router.register_provider("provider2", provider2, {})

    request = LLMRequest(system_prompt="test", user_prompt="hello")
    response = await router.complete(request, provider_name="provider2")
    assert "model2" in response.content


@pytest.mark.asyncio
async def test_router_complete_provider_not_configured() -> None:
    """Test completion with non-configured provider raises error."""
    router = LLMRouter[StructuredResponse]()
    request = LLMRequest(system_prompt="test", user_prompt="hello")
    with pytest.raises(ProviderNotConfiguredError):
        await router.complete(request, provider_name="nonexistent")


@pytest.mark.asyncio
async def test_router_complete_structured() -> None:
    """Test structured completion."""
    router = LLMRouter[StructuredResponse](default_provider_name="mock")
    provider = MockProvider()
    router.register_provider("mock", provider, {})

    request = LLMRequest(system_prompt="test", user_prompt="hello")
    response = await router.complete_structured(request, StructuredResponse)
    assert isinstance(response, StructuredResponse)
    assert "Mock structured response" in response.content


# --- Router Error Tests ---

def test_router_error_base() -> None:
    """Test base RouterError."""
    error = RouterError("Routing failed")
    assert str(error) == "Routing failed"


def test_provider_not_configured_error_message() -> None:
    """Test ProviderNotConfiguredError message."""
    error = ProviderNotConfiguredError("provider 'test' not configured")
    assert "provider 'test' not configured" in str(error)
