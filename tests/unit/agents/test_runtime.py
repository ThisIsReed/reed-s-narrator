from __future__ import annotations

from typing import Any

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


class SequenceLLMClient:
    def __init__(self, responses: dict[type[BaseModel], list[BaseModel]]) -> None:
        self._responses = {key: list(value) for key, value in responses.items()}
        self.requests: list[LLMRequest] = []

    async def complete_structured(
        self,
        request: LLMRequest,
        response_type: type[BaseModel],
        provider_name: str | None = None,
    ) -> BaseModel:
        self.requests.append(request)
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


def build_context() -> CharacterKnowledgeContext:
    return CharacterKnowledgeContext(character_id="hero", tick=5)


def build_world() -> WorldState:
    return WorldState(
        tick=5,
        seed=99,
        granularity=Granularity.DAY,
        characters={"hero": build_character()},
        resources={"food": 10.0},
    )


def build_whitelist() -> ActionWhitelist:
    return ActionWhitelist(
        version=1,
        actions={
            "move": ActionRule(required_params=("destination",), optional_params=("pace",)),
            "rest": ActionRule(required_params=(), optional_params=("duration_hours",)),
        },
    )


def build_settlement(intent: IntentPayload) -> SettlementContext:
    return SettlementContext(
        tick=5,
        character=build_character(),
        intent=intent,
        world=build_world(),
        rule_summary=("travel_cost",),
        rng_seed=99,
    )


@pytest.mark.asyncio
async def test_character_agent_returns_validated_intent() -> None:
    client = SequenceLLMClient(
        {
            IntentResponse: [
                IntentResponse(
                    intent="move",
                    flavor_text="他沿着小路前往营地。",
                    parameters={"destination": "camp", "pace": "steady"},
                )
            ]
        }
    )
    agent = CharacterAgent(client, build_whitelist())

    intent = await agent.generate_intent(build_character(), build_context())

    assert intent.action_type == "move"
    assert intent.parameters["destination"] == "camp"
    assert len(client.requests) == 1


@pytest.mark.asyncio
async def test_dm_agent_maps_structured_response_to_action_result() -> None:
    client = SequenceLLMClient(
        {
            DecisionResponse: [
                DecisionResponse(
                    verdict="ACCEPT",
                    reason="path is clear",
                    outcome={
                        "flavor_text": "他顺利抵达营地。",
                        "state_changes": [
                            {
                                "path": "resources.food",
                                "before": 10.0,
                                "after": 9.0,
                                "reason": "travel_cost",
                            }
                        ],
                    },
                )
            ]
        }
    )
    agent = DMAgent(client)
    context = build_settlement(
        IntentPayload(
            character_id="hero",
            action_type="move",
            parameters={"destination": "camp"},
            flavor_text="他想回营地。",
        )
    )

    result = await agent.settle(context)

    assert result.verdict is Verdict.APPROVED
    assert result.verdict_reason == "path is clear"
    assert result.state_changes[0].after == 9.0
    assert result.flavor_text == "他顺利抵达营地。"


@pytest.mark.asyncio
async def test_retry_coordinator_retries_then_runs_dm() -> None:
    client = SequenceLLMClient(
        {
            IntentResponse: [
                IntentResponse(
                    intent="move",
                    flavor_text="先侦察再前进。",
                    parameters={"destination": "camp"},
                ),
                IntentResponse(
                    intent="move",
                    flavor_text="确认安全后前往营地。",
                    parameters={"destination": "camp"},
                ),
            ],
            DecisionResponse: [
                DecisionResponse(
                    verdict="APPROVED",
                    reason="approved after clarification",
                    outcome={"state_changes": []},
                )
            ],
        }
    )
    character_agent = CharacterAgent(client, build_whitelist())
    dm_agent = DMAgent(client)
    decisions = iter(
        (
            NarratorDecision(verdict=Verdict.REJECTED, reason="needs safer route"),
            NarratorDecision(verdict=Verdict.APPROVED, reason="route approved"),
        )
    )

    coordinator = RetryCoordinator(
        character_agent=character_agent,
        dm_agent=dm_agent,
        narrator_judge=lambda _: next(decisions),
        fallback_resolver=lambda _: _fallback_result(),
        max_retry=2,
    )

    outcome = await coordinator.execute(build_character(), build_context(), build_settlement)

    assert outcome.result.verdict is Verdict.APPROVED
    assert outcome.result.retry_count == 1
    assert len(outcome.attempts) == 2
    assert outcome.attempts[0].reason == "needs safer route"
    assert outcome.result.verdict_reason == "approved after clarification"


@pytest.mark.asyncio
async def test_retry_coordinator_falls_back_after_invalid_intents() -> None:
    client = SequenceLLMClient(
        {
            IntentResponse: [
                IntentResponse(
                    intent="teleport",
                    flavor_text="直接闪现到营地。",
                    parameters={},
                ),
                IntentResponse(
                    intent="teleport",
                    flavor_text="再次尝试闪现。",
                    parameters={},
                ),
            ]
        }
    )
    coordinator = RetryCoordinator(
        character_agent=CharacterAgent(client, build_whitelist()),
        dm_agent=DMAgent(SequenceLLMClient({})),
        narrator_judge=lambda _: NarratorDecision(verdict=Verdict.APPROVED, reason="unused"),
        fallback_resolver=lambda _: _fallback_result(),
        max_retry=1,
    )

    outcome = await coordinator.execute(build_character(), build_context(), build_settlement)

    assert outcome.result.verdict is Verdict.FALLBACK
    assert outcome.result.is_fallback is True
    assert outcome.result.retry_count == 1
    assert outcome.result.fallback_reason == "action not allowed: teleport"
    assert len(outcome.attempts) == 2


def _fallback_result() -> ActionResult:
    return ActionResult(
        action=Action(
            character_id="hero",
            action_type="rest",
            parameters={"duration_hours": 1},
        ),
        verdict=Verdict.APPROVED,
        flavor_text="他选择原地休整。",
    )
