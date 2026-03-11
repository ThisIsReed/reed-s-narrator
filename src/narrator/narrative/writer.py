"""Narrative rendering and LLM polishing."""

from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel

from narrator.llm import LLMRequest
from narrator.llm.schemas import NarrativeSummaryResponse

from .models import NarrativeBeat, NarrativeEntry

DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 384


class NarrativeWriterError(RuntimeError):
    """Raised when narrative generation fails validation."""


class StructuredNarrativeClient(Protocol):
    async def complete_structured(
        self,
        request: LLMRequest,
        response_type: type[BaseModel],
        provider_name: str | None = None,
    ) -> BaseModel: ...


class NarrativeWriter:
    def __init__(
        self,
        llm_client: StructuredNarrativeClient,
        provider_name: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._llm_client = llm_client
        self._provider_name = provider_name
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def write(self, beat: NarrativeBeat) -> NarrativeEntry:
        request = LLMRequest(
            system_prompt=_system_prompt(),
            user_prompt=_user_prompt(beat),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        response = await self._llm_client.complete_structured(
            request,
            NarrativeSummaryResponse,
            provider_name=self._provider_name,
        )
        return _validate_entry(beat, response)


def render_rule_entry(beat: NarrativeBeat) -> NarrativeEntry:
    summary_text = " ".join((beat.background, beat.action, beat.result, beat.outlook))
    return NarrativeEntry(
        tick=beat.tick,
        title=beat.title,
        summary_text=summary_text,
        source_refs=beat.source_refs,
        mentioned_character_ids=beat.mentioned_character_ids,
        mentioned_event_ids=beat.mentioned_event_ids,
    )


def _system_prompt() -> str:
    return (
        "你是全知旁白，只能改写给定事实，不能补写新事件、新状态或新因果。"
        "输出一段简洁的中文回合纪要，并保留角色与事件的可追溯性。"
    )


def _user_prompt(beat: NarrativeBeat) -> str:
    return json.dumps(beat.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _validate_entry(beat: NarrativeBeat, response: BaseModel) -> NarrativeEntry:
    raw = response.model_dump()
    summary_text = raw["summary_text"].strip()
    if not summary_text:
        raise NarrativeWriterError("narrative summary_text must not be empty")
    _validate_mentions("character", raw["mentioned_character_ids"], beat.mentioned_character_ids)
    _validate_mentions("event", raw["mentioned_event_ids"], beat.mentioned_event_ids)
    return NarrativeEntry(
        tick=beat.tick,
        title=raw["title"],
        summary_text=summary_text,
        source_refs=beat.source_refs,
        mentioned_character_ids=tuple(raw["mentioned_character_ids"]),
        mentioned_event_ids=tuple(raw["mentioned_event_ids"]),
    )


def _validate_mentions(kind: str, received: list[str], allowed: tuple[str, ...]) -> None:
    unknown = sorted(set(received) - set(allowed))
    if unknown:
        names = ",".join(unknown)
        raise NarrativeWriterError(f"unknown {kind} references in narrative output: {names}")
