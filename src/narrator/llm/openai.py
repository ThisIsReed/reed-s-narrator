"""OpenAI LLM Provider implementation."""

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


class OpenAIProvider(LLMProvider[T]):
    """OpenAI API provider implementation."""

    def __init__(
        self, model: str, api_key: str, base_url: str = "https://api.openai.com/v1", **kwargs: Any
    ) -> None:
        """Initialize the OpenAI provider.

        Args:
            model: The model identifier (e.g., "gpt-4", "gpt-3.5-turbo")
            api_key: OpenAI API key
            base_url: API base URL (default: https://api.openai.com/v1)
            **kwargs: Additional configuration
        """
        super().__init__(model, **kwargs)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_tokens = kwargs.get("max_tokens", 1024)
        self._timeout = kwargs.get("timeout", 30.0)

    async def health_check(self) -> HealthCheckResponse:
        """Check if the OpenAI API is available."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                if response.status_code == 200:
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
                    "messages": [
                        {"role": "system", "content": request.system_prompt},
                        {"role": "user", "content": request.user_prompt},
                    ],
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens or self._max_tokens,
                    "top_p": request.top_p,
                }

                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code != 200:
                    raise ProviderError(f"API error: {response.status_code} - {response.text}")

                data = response.json()
                content = data["choices"][0]["message"]["content"]

                usage = {}
                if "usage" in data:
                    usage = {
                        "prompt_tokens": data["usage"].get("prompt_tokens", 0),
                        "completion_tokens": data["usage"].get("completion_tokens", 0),
                        "total_tokens": data["usage"].get("total_tokens", 0),
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
            # Try to use JSON mode if the model supports it
            schema_json = response_type.model_json_schema()

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                payload = {
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": request.system_prompt},
                        {
                            "role": "user",
                            "content": request.user_prompt
                            + f"\n\nRespond with a valid JSON matching this schema: {json.dumps(schema_json)}",
                        },
                    ],
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens or self._max_tokens,
                    "top_p": request.top_p,
                    "response_format": {"type": "json_object"},
                }

                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code != 200:
                    raise ProviderError(f"API error: {response.status_code} - {response.text}")

                data = response.json()
                content = data["choices"][0]["message"]["content"]

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
