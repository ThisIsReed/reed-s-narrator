from __future__ import annotations

from narrator.knowledge import (
    Belief,
    BeliefStore,
    Fact,
    FactStore,
    FactVisibility,
    KnowledgeAssembler,
)
from narrator.models import Character, StateMode


def build_character(character_id: str, location_id: str) -> Character:
    return Character(
        id=character_id,
        name=character_id.title(),
        state_mode=StateMode.ACTIVE,
        location_id=location_id,
    )


def test_context_only_contains_authorized_facts_and_permitted_clues() -> None:
    hero = build_character("hero", "market")
    rival = build_character("rival", "palace")
    fact_store = FactStore(
        (
            Fact(id="fact-public", tick_created=1, content="钟楼敲了三下。"),
            Fact(
                id="fact-palace",
                tick_created=1,
                content="王宫卫队今晚换防。",
                visibility=FactVisibility(scope="location", location_ids=("palace",)),
            ),
            Fact(
                id="fact-secret",
                tick_created=1,
                content="密道入口在祭坛后。",
                visibility=FactVisibility(scope="private", character_ids=("rival",)),
            ),
        )
    )
    belief_store = BeliefStore(
        (
            Belief(
                character_id="hero",
                belief_id="rumor-secret",
                summary="有人传言祭坛附近藏着不该出现的脚印。",
                acquired_tick=2,
                fact_id="fact-secret",
                confidence=0.4,
                source_type="rumor",
            ),
        )
    )
    assembler = KnowledgeAssembler(fact_store, belief_store)

    hero_context = assembler.build_context(hero, tick=3)
    rival_context = assembler.build_context(rival, tick=3)

    assert tuple(entry.entry_id for entry in hero_context.facts) == ("fact-public",)
    assert tuple(entry.entry_id for entry in hero_context.clues) == ("rumor-secret",)
    assert all("密道入口" not in entry.content for entry in hero_context.clues)
    assert tuple(entry.entry_id for entry in rival_context.facts) == (
        "fact-palace",
        "fact-public",
        "fact-secret",
    )


def test_context_build_is_reproducible_and_auditable() -> None:
    scholar = build_character("scholar", "archive")
    fact_store = FactStore(
        (
            Fact(id="fact-a", tick_created=1, content="档案馆昨夜停电。"),
            Fact(
                id="fact-b",
                tick_created=1,
                content="地下室封存室被重新上锁。",
                visibility=FactVisibility(scope="private", character_ids=("scholar",)),
            ),
        )
    )
    belief_store = BeliefStore(
        (
            Belief(
                character_id="scholar",
                belief_id="inference-a",
                summary="停电很可能与封存室检查有关。",
                acquired_tick=2,
                confidence=0.7,
                source_type="inference",
            ),
        )
    )
    assembler = KnowledgeAssembler(fact_store, belief_store)

    first = assembler.build_context(scholar, tick=4)
    second = assembler.build_context(scholar, tick=4)

    assert first == second
    assert first.audit_log == (
        "character=scholar",
        "location=archive",
        "visible_facts=fact-a,fact-b",
        "beliefs=inference-a",
        "clues=inference-a",
    )
