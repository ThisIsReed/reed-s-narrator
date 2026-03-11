from __future__ import annotations

import pytest

from narrator.narrative import NarrativeBeat, NarrativeWriter, NarrativeWriterError, render_rule_entry


class FakeNarrativeClient:
    def __init__(self, response_payload: dict[str, object]) -> None:
        self._response_payload = response_payload

    async def complete_structured(self, request, response_type, provider_name=None):
        return response_type.model_validate(self._response_payload)


def build_beat() -> NarrativeBeat:
    return NarrativeBeat(
        tick=3,
        title="第 3 回合",
        priority="action",
        background="背景推进：市场风声渐紧。",
        action="关键行动：merchant：Merchant hides the ledger before inspectors arrive.。",
        result="结果变化：merchant_actions 从 0.0 变为 1.0。",
        outlook="未完事项：alarm-3 尚未解决。",
        mentioned_character_ids=("merchant",),
        mentioned_event_ids=("alarm-3",),
        source_refs=("snapshot:3", "action_log:3", "tick_audit:3"),
    )


def test_render_rule_entry_is_deterministic() -> None:
    beat = build_beat()

    first = render_rule_entry(beat)
    second = render_rule_entry(beat)

    assert first == second


@pytest.mark.asyncio
async def test_narrative_writer_rejects_unknown_mentions() -> None:
    beat = build_beat()
    writer = NarrativeWriter(
        FakeNarrativeClient(
            {
                "title": beat.title,
                "summary_text": "市场上的账本被藏起，局势仍未落定。",
                "mentioned_character_ids": ["merchant", "guard"],
                "mentioned_event_ids": ["alarm-3"],
            }
        )
    )

    with pytest.raises(NarrativeWriterError, match="unknown character references"):
        await writer.write(beat)
