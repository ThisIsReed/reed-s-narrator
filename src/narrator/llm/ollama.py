"""Ollama LLM Provider implementation."""

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


class OllamaProvider(LLMProvider[T]):
    """Ollama API provider implementation."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        **kwargs: Any,
    ) -> None:
        """Initialize the Ollama provider.

        Args:
            model: The model identifier (e.g., "llama2", "mistral", "codellama")
            base_url: Ollama API base URL (default: http://localhost:11434)
            **kwargs: Additional configuration
        """
        super().__init__(model, **kwargs)
        self._base_url = base_url.rstrip("/")
        self._num_predict = kwargs.get("num_predict", 1024)
        self._timeout = kwargs.get("timeout", 60.0)

    async def health_check(self) -> HealthCheckResponse:
        """Check if the Ollama API is available."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._base_url}/api/tags")
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
                    "prompt": request.user_prompt,
                    "system": request.system_prompt,
                    "stream": False,
                    "options": {
                        "temperature": request.temperature,
                        "top_p": request.top_p,
                        "num_predict": request.max_tokens or self._num_predict,
                    },
                }

                response = await client.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                )

                if response.status_code != 200:
                    raise ProviderError(f"API error: {response.status_code} - {response.text}")

                data = response.json()
                content = data.get("response", "")

                usage = {
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                    "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
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

            # Add schema instructions to the prompt
            user_prompt = (
                f"{request.user_prompt}\n\n"
                f"Respond with a valid JSON object matching this schema: {json.dumps(schema_json)}"
            )

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                payload = {
                    "model": self._model,
                    "prompt": user_prompt,
                    "system": request.system_prompt,
                    "format": "json",  # Ollama's JSON mode
                    "stream": False,
                    "options": {
                        "temperature": request.temperature,
                        "top_p": request.top_p,
                        "num_predict": request.max_tokens or self._num_predict,
                    },
                }

                response = await client.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                )

                if response.status_code != 200:
                    raise ProviderError(f"API error: {response.status_code} - {response.text}")

                data = response.json()
                content = data.get("response", "")

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
