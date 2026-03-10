from __future__ import annotations

import pytest
from pydantic import BaseModel

from narrator.agents import (
    CharacterAgent,
    DMAgent,
    NarratorDecision,
    RetryCoordinator,
    SettlementContext,
)
from narrator.agents.intent import ActionWhitelist, ActionRule, IntentPayload
from narrator.knowledge import CharacterKnowledgeContext
from narrator.llm.base import LLMRequest
from narrator.llm.schemas import DecisionResponse, IntentResponse
from narrator.models import (
    Action,
    ActionResult,
    Character,
    Granularity,
    StateMode,
    Verdict,
    WorldState,
)
from narrator.persistence import ActionLogRepository, SQLiteDatabase


class SequenceLLMClient:
    def __init__(self, responses: dict[type[BaseModel], list[BaseModel]]) -> None:
        self._responses = {key: list(value) for key, value in responses.items()}

    async def complete_structured(
        self,
        request: LLMRequest,
        response_type: type[BaseModel],
        provider_name: str | None = None,
    ) -> BaseModel:
        queue = self._responses.get(response_type, [])
        if not queue:
            raise AssertionError(f"missing mock response for {response_type.__name__}")
        return queue.pop(0)


def build_character() -> Character:
    return Character(
        id="hero",
        name="Hero",
        state_mode=StateMode.ACTIVE,
        location_id="camp",
    )


def build_world() -> WorldState:
    character = build_character()
    return WorldState(
        tick=8,
        seed=21,
        granularity=Granularity.DAY,
        characters={character.id: character},
    )


def build_whitelist() -> ActionWhitelist:
    return ActionWhitelist(
        version=1,
        actions={"move": ActionRule(required_params=("destination",), optional_params=())},
    )


def build_settlement(intent: IntentPayload) -> SettlementContext:
    return SettlementContext(
        tick=8,
        character=build_character(),
        intent=intent,
        world=build_world(),
        rule_summary=("camp_safe",),
        rng_seed=21,
    )


@pytest.mark.asyncio
async def test_agent_flow_result_can_be_persisted(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "narrator.db")
    database.initialize()
    client = SequenceLLMClient(
        {
            IntentResponse: [
                IntentResponse(
                    intent="move",
                    flavor_text="他谨慎向营地靠近。",
                    parameters={"destination": "camp"},
                ),
                IntentResponse(
                    intent="move",
                    flavor_text="他确认口令后进入营地。",
                    parameters={"destination": "camp"},
                ),
            ],
            DecisionResponse: [
                DecisionResponse(
                    verdict="ACCEPT",
                    reason="gate is open",
                    outcome={"state_changes": []},
                )
            ],
        }
    )
    coordinator = RetryCoordinator(
        character_agent=CharacterAgent(client, build_whitelist()),
        dm_agent=DMAgent(client),
        narrator_judge=_judge_once_then_approve,
        fallback_resolver=lambda _: _fallback_result(),
        max_retry=2,
    )
    context = CharacterKnowledgeContext(character_id="hero", tick=8)

    outcome = await coordinator.execute(build_character(), context, build_settlement)

    with database.connect() as connection:
        repository = ActionLogRepository(connection)
        repository.save(tick=8, result=outcome.result)
        stored = repository.list_by_tick(8)

    assert outcome.result.retry_count == 1
    assert stored == (outcome.result,)


def _judge_once_then_approve(evaluation) -> NarratorDecision:
    if evaluation.intent.flavor_text == "他谨慎向营地靠近。":
        return NarratorDecision(verdict=Verdict.REJECTED, reason="need password check")
    return NarratorDecision(verdict=Verdict.APPROVED, reason="approved")


def _fallback_result() -> ActionResult:
    return ActionResult(
        action=Action(
            character_id="hero",
            action_type="move",
            parameters={"destination": "camp"},
        ),
        verdict=Verdict.APPROVED,
        flavor_text="他留在原地等待。",
    )
