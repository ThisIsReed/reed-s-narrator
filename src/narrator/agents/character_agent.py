"""Character agent for intent generation."""

from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import BaseModel

from narrator.agents.intent import (
    ActionWhitelist,
    IntentPayload,
    validate_intent,
)
from narrator.knowledge import CharacterKnowledgeContext
from narrator.llm.base import LLMRequest
from narrator.llm.schemas import IntentResponse
from narrator.models import Character

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 512


class StructuredLLMClient(Protocol):
    async def complete_structured(
        self,
        request: LLMRequest,
        response_type: type[BaseModel],
        provider_name: str | None = None,
    ) -> BaseModel: ...


class CharacterAgent:
    def __init__(
        self,
        llm_client: StructuredLLMClient,
        whitelist: ActionWhitelist,
        provider_name: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._llm_client = llm_client
        self._whitelist = whitelist
        self._provider_name = provider_name
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def generate_intent(
        self,
        character: Character,
        context: CharacterKnowledgeContext,
    ) -> IntentPayload:
        request = self._build_request(character, context)
        response = await self._llm_client.complete_structured(
            request,
            IntentResponse,
            provider_name=self._provider_name,
        )
        return validate_intent(self._to_payload(character.id, response), self._whitelist)

    def _build_request(
        self,
        character: Character,
        context: CharacterKnowledgeContext,
    ) -> LLMRequest:
        return LLMRequest(
            system_prompt=_build_system_prompt(self._whitelist),
            user_prompt=_build_user_prompt(character, context),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )

    @staticmethod
    def _to_payload(character_id: str, response: BaseModel) -> dict[str, Any]:
        raw = response.model_dump()
        return {
            "character_id": character_id,
            "action_type": raw["intent"],
            "parameters": raw["parameters"],
            "flavor_text": raw["flavor_text"],
        }


def _build_system_prompt(whitelist: ActionWhitelist) -> str:
    action_rules = {
        action_type: {
            "required_params": rule.required_params,
            "optional_params": rule.optional_params,
        }
        for action_type, rule in whitelist.actions.items()
    }
    rule_json = json.dumps(action_rules, ensure_ascii=False, sort_keys=True)
    return (
        "You are the character intent planner. "
        "Return one allowed action only. "
        f"Allowed actions: {rule_json}"
    )


def _build_user_prompt(
    character: Character,
    context: CharacterKnowledgeContext,
) -> str:
    payload = {
        "character": character.model_dump(mode="json"),
        "knowledge_context": context.model_dump(mode="json"),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
