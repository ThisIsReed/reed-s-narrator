"""Retry and fallback coordination for agent execution."""

from __future__ import annotations

from typing import Protocol

from pydantic import Field, model_validator

from narrator.agents.character_agent import CharacterAgent
from narrator.agents.dm_agent import DMAgent, SettlementContext
from narrator.agents.intent import IntentPayload, IntentValidationError
from narrator.knowledge import CharacterKnowledgeContext
from narrator.models import ActionResult, Character, Verdict
from narrator.models.base import DomainModel


class NarratorDecision(DomainModel):
    verdict: Verdict
    reason: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_verdict(self) -> "NarratorDecision":
        if self.verdict is Verdict.FALLBACK:
            raise ValueError("NarratorDecision cannot use FALLBACK verdict")
        return self


class NarratorEvaluation(DomainModel):
    character: Character
    context: CharacterKnowledgeContext
    intent: IntentPayload


class RetryAttempt(DomainModel):
    attempt_index: int = Field(..., ge=0)
    verdict: Verdict
    reason: str = Field(..., min_length=1)
    intent: IntentPayload | None = None


class RetryOutcome(DomainModel):
    result: ActionResult
    attempts: tuple[RetryAttempt, ...]


class FallbackInput(DomainModel):
    character: Character
    context: CharacterKnowledgeContext
    failure_reason: str = Field(..., min_length=1)
    retry_count: int = Field(..., ge=0)


class NarratorJudge(Protocol):
    def __call__(self, evaluation: NarratorEvaluation) -> NarratorDecision: ...


class FallbackResolver(Protocol):
    def __call__(self, fallback_input: FallbackInput) -> ActionResult: ...


class SettlementFactory(Protocol):
    def __call__(self, intent: IntentPayload) -> SettlementContext: ...


class RetryCoordinator:
    def __init__(
        self,
        character_agent: CharacterAgent,
        dm_agent: DMAgent,
        narrator_judge: NarratorJudge,
        fallback_resolver: FallbackResolver,
        max_retry: int,
    ) -> None:
        self._character_agent = character_agent
        self._dm_agent = dm_agent
        self._narrator_judge = narrator_judge
        self._fallback_resolver = fallback_resolver
        self._max_retry = max_retry

    async def execute(
        self,
        character: Character,
        context: CharacterKnowledgeContext,
        settlement_factory: SettlementFactory,
    ) -> RetryOutcome:
        attempts: list[RetryAttempt] = []
        for attempt_index in range(self._max_retry + 1):
            intent = await self._generate_intent(character, context, attempts, attempt_index)
            if intent is None:
                continue
            decision = self._narrator_judge(
                NarratorEvaluation(character=character, context=context, intent=intent)
            )
            attempts.append(
                RetryAttempt(
                    attempt_index=attempt_index,
                    verdict=decision.verdict,
                    reason=decision.reason,
                    intent=intent,
                )
            )
            if decision.verdict is Verdict.APPROVED:
                return await self._settle(intent, settlement_factory, attempts, attempt_index)
        return self._build_fallback(character, context, attempts)

    async def _generate_intent(
        self,
        character: Character,
        context: CharacterKnowledgeContext,
        attempts: list[RetryAttempt],
        attempt_index: int,
    ) -> IntentPayload | None:
        try:
            return await self._character_agent.generate_intent(character, context)
        except IntentValidationError as exc:
            attempts.append(
                RetryAttempt(
                    attempt_index=attempt_index,
                    verdict=Verdict.REJECTED,
                    reason=str(exc),
                )
            )
            return None

    async def _settle(
        self,
        intent: IntentPayload,
        settlement_factory: SettlementFactory,
        attempts: list[RetryAttempt],
        retry_count: int,
    ) -> RetryOutcome:
        result = await self._dm_agent.settle(settlement_factory(intent))
        final_result = result.model_copy(update={"retry_count": retry_count})
        return RetryOutcome(result=final_result, attempts=tuple(attempts))

    def _build_fallback(
        self,
        character: Character,
        context: CharacterKnowledgeContext,
        attempts: list[RetryAttempt],
    ) -> RetryOutcome:
        reason = attempts[-1].reason
        fallback = self._fallback_resolver(
            FallbackInput(
                character=character,
                context=context,
                failure_reason=reason,
                retry_count=self._max_retry,
            )
        )
        final_result = fallback.model_copy(
            update={
                "verdict": Verdict.FALLBACK,
                "verdict_reason": reason,
                "retry_count": self._max_retry,
                "is_fallback": True,
                "fallback_reason": reason,
            }
        )
        return RetryOutcome(result=final_result, attempts=tuple(attempts))
