"""DM agent for stateless settlement."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from narrator.agents.character_agent import StructuredLLMClient
from narrator.agents.intent import IntentPayload
from narrator.llm.base import LLMRequest
from narrator.llm.schemas import DecisionResponse
from narrator.models import Action, ActionResult, Character, StateChange, Verdict, WorldState
from narrator.models.base import DomainModel

DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 768
APPROVED_VERDICTS = frozenset({"ACCEPT", "APPROVED"})
REJECTED_VERDICTS = frozenset({"REJECT", "REJECTED"})


class DMAgentError(RuntimeError):
    """Raised when settlement output is invalid."""


class SettlementContext(DomainModel):
    tick: int = Field(..., ge=0)
    character: Character
    intent: IntentPayload
    world: WorldState
    rule_summary: tuple[str, ...] = ()
    rng_seed: int | None = None


class DMAgent:
    def __init__(
        self,
        llm_client: StructuredLLMClient,
        provider_name: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._llm_client = llm_client
        self._provider_name = provider_name
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def settle(self, context: SettlementContext) -> ActionResult:
        request = self._build_request(context)
        response = await self._llm_client.complete_structured(
            request,
            DecisionResponse,
            provider_name=self._provider_name,
        )
        return _build_result(context.intent, response)

    def _build_request(self, context: SettlementContext) -> LLMRequest:
        return LLMRequest(
            system_prompt=_build_system_prompt(),
            user_prompt=_build_user_prompt(context),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )


def _build_system_prompt() -> str:
    return (
        "You are the stateless DM. "
        "Evaluate the approved intent and return a structured settlement result."
    )


def _build_user_prompt(context: SettlementContext) -> str:
    return json.dumps(context.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _build_result(intent: IntentPayload, response: BaseModel) -> ActionResult:
    raw = response.model_dump()
    verdict = _parse_verdict(raw["verdict"])
    return ActionResult(
        action=Action(
            character_id=intent.character_id,
            action_type=intent.action_type,
            parameters=intent.parameters,
            target_id=intent.target_id,
        ),
        verdict=verdict,
        verdict_reason=raw["reason"],
        state_changes=_parse_state_changes(raw["outcome"]),
        flavor_text=_parse_flavor_text(raw["outcome"], intent.flavor_text),
    )


def _parse_verdict(raw_verdict: str) -> Verdict:
    normalized = raw_verdict.strip().upper()
    if normalized in APPROVED_VERDICTS:
        return Verdict.APPROVED
    if normalized in REJECTED_VERDICTS:
        return Verdict.REJECTED
    raise DMAgentError(f"unsupported DM verdict: {raw_verdict}")


def _parse_state_changes(outcome: dict[str, Any]) -> tuple[StateChange, ...]:
    raw_changes = outcome.get("state_changes", ())
    try:
        return tuple(StateChange.model_validate(change) for change in raw_changes)
    except ValidationError as exc:
        raise DMAgentError("invalid DM state_changes payload") from exc


def _parse_flavor_text(outcome: dict[str, Any], default_text: str) -> str:
    flavor_text = outcome.get("flavor_text")
    if flavor_text is None:
        return default_text
    if not isinstance(flavor_text, str) or not flavor_text.strip():
        raise DMAgentError("invalid DM flavor_text payload")
    return flavor_text
