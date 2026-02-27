"""Anthropic LLM Provider implementation."""

from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx

from .base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
    ProviderUnavailableError,
    ProviderValidationError,
)
from .schemas import HealthCheckResponse, StructuredResponse, validate_structured_response

T = TypeVar("T", bound=StructuredResponse)


class AnthropicProvider(LLMProvider[T]):
    """Anthropic API provider implementation."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        **kwargs: Any,
    ) -> None:
        """Initialize the Anthropic provider.

        Args:
            model: The model identifier (e.g., "claude-3-opus-20240229", "claude-3-sonnet-20240229")
            api_key: Anthropic API key
            base_url: API base URL (default: https://api.anthropic.com)
            **kwargs: Additional configuration
        """
        super().__init__(model, **kwargs)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_tokens = kwargs.get("max_tokens", 1024)
        self._timeout = kwargs.get("timeout", 30.0)
        self._api_version = kwargs.get("api_version", "2023-06-01")

    async def health_check(self) -> HealthCheckResponse:
        """Check if the Anthropic API is available."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # Anthropic doesn't have a dedicated health endpoint
                # We'll do a minimal test request
                response = await client.post(
                    f"{self._base_url}/v1/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": self._api_version,
                        "content-type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "."}],
                    },
                )
                # We expect either a success or a rate limit error (which means API is up)
                if response.status_code in (200, 429):
                    return HealthCheckResponse(healthy=True, message="OK")
                return HealthCheckResponse(
                    healthy=False, message=f"status code: {response.status_code}"
                )
        except httpx.ConnectError as e:
            return HealthCheckResponse(healthy=False, message=f"connection failed: {e}")
        except Exception as e:
            return HealthCheckResponse(healthy=False, message=str(e))

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Perform a standard completion request."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                payload = {
                    "model": self._model,
                    "max_tokens": request.max_tokens or self._max_tokens,
                    "messages": [{"role": "user", "content": request.user_prompt}],
                    "system": request.system_prompt,
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                }

                response = await client.post(
                    f"{self._base_url}/v1/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": self._api_version,
                        "content-type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code != 200:
                    raise ProviderError(f"API error: {response.status_code} - {response.text}")

                data = response.json()
                content = data["content"][0]["text"]

                usage = {}
                if "usage" in data:
                    usage = {
                        "input_tokens": data["usage"].get("input_tokens", 0),
                        "output_tokens": data["usage"].get("output_tokens", 0),
                    }

                return LLMResponse(
                    content=content,
                    model=self._model,
                    usage=usage,
                    raw_response=data,
                )

        except httpx.ConnectError as e:
            raise ProviderUnavailableError(f"connection failed: {e}") from e
        except Exception as e:
            if isinstance(e, ProviderError):
                raise
            raise ProviderError(f"unexpected error: {e}") from e

    async def complete_structured(
        self, request: LLMRequest, response_type: type[T]
    ) -> T:
        """Perform a completion request with structured output."""
        try:
            schema_json = response_type.model_json_schema()

            # Use Anthropic's tool/system prompt approach for structured output
            system_prompt = (
                f"{request.system_prompt}\n\n"
                f"You must respond with a valid JSON object matching this schema: {json.dumps(schema_json)}"
            )

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                payload = {
                    "model": self._model,
                    "max_tokens": request.max_tokens or self._max_tokens,
                    "messages": [{"role": "user", "content": request.user_prompt}],
                    "system": system_prompt,
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                }

                response = await client.post(
                    f"{self._base_url}/v1/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": self._api_version,
                        "content-type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code != 200:
                    raise ProviderError(f"API error: {response.status_code} - {response.text}")

                data = response.json()
                content = data["content"][0]["text"]

                # Parse and validate the JSON response
                try:
                    response_data = json.loads(content)
                except json.JSONDecodeError as e:
                    raise ProviderValidationError(f"invalid JSON in response: {e}") from e

                # Validate against the schema
                is_valid, validated, error_msg = validate_structured_response(
                    response_data, response_type
                )
                if not is_valid or validated is None:
                    raise ProviderValidationError(f"schema validation failed: {error_msg}")

                return validated

        except httpx.ConnectError as e:
            raise ProviderUnavailableError(f"connection failed: {e}") from e
        except Exception as e:
            if isinstance(e, (ProviderError, ProviderValidationError)):
                raise
            raise ProviderError(f"unexpected error: {e}") from e
