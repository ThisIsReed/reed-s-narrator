from __future__ import annotations

import pytest
from pydantic import ValidationError

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
        name=character_id,
        state_mode=StateMode.ACTIVE,
        location_id=location_id,
    )


def test_location_visibility_requires_targets() -> None:
    with pytest.raises(ValidationError):
        FactVisibility(scope="location")


def test_fact_store_filters_by_scope() -> None:
    square = build_character("c-1", "square")
    fact_store = FactStore(
        (
            Fact(id="global", tick_created=0, content="A"),
            Fact(
                id="local",
                tick_created=0,
                content="B",
                visibility=FactVisibility(scope="location", location_ids=("square",)),
            ),
            Fact(
                id="private",
                tick_created=0,
                content="C",
                visibility=FactVisibility(scope="private", character_ids=("c-2",)),
            ),
        )
    )

    visible = fact_store.list_visible_for(square)

    assert tuple(fact.id for fact in visible) == ("global", "local")


def test_knowledge_assembler_skips_clue_when_fact_already_visible() -> None:
    hero = build_character("hero", "camp")
    fact_store = FactStore((Fact(id="fact-1", tick_created=1, content="Visible"),))
    belief_store = BeliefStore(
        (
            Belief(
                character_id="hero",
                belief_id="belief-1",
                summary="Visible",
                acquired_tick=1,
                fact_id="fact-1",
            ),
        )
    )
    assembler = KnowledgeAssembler(fact_store, belief_store)

    context = assembler.build_context(hero, tick=1)

    assert tuple(entry.entry_id for entry in context.facts) == ("fact-1",)
    assert context.clues == ()


def test_plan_diffusion_rejects_negative_delay() -> None:
    assembler = KnowledgeAssembler(FactStore(), BeliefStore())
    belief = Belief(
        character_id="hero",
        belief_id="belief-1",
        summary="A rumor",
        acquired_tick=3,
        source_type="rumor",
    )

    with pytest.raises(ValueError):
        assembler.plan_diffusion(belief, target_character_id="ally", delay_ticks=-1)
