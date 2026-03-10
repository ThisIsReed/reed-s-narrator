"""Knowledge context building and diffusion planning."""

from __future__ import annotations

from pydantic import Field

from narrator.knowledge.belief_store import Belief, BeliefStore
from narrator.knowledge.fact_store import Fact, FactStore
from narrator.models.base import DomainModel
from narrator.models.character import Character


class KnowledgeEntry(DomainModel):
    entry_id: str = Field(..., min_length=1)
    entry_type: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_refs: tuple[str, ...] = ()


class CharacterKnowledgeContext(DomainModel):
    character_id: str = Field(..., min_length=1)
    tick: int = Field(..., ge=0)
    facts: tuple[KnowledgeEntry, ...] = ()
    clues: tuple[KnowledgeEntry, ...] = ()
    audit_log: tuple[str, ...] = ()


class PropagationTask(DomainModel):
    belief_id: str = Field(..., min_length=1)
    origin_character_id: str = Field(..., min_length=1)
    target_character_id: str = Field(..., min_length=1)
    available_at_tick: int = Field(..., ge=0)


class KnowledgeAssembler:
    def __init__(self, fact_store: FactStore, belief_store: BeliefStore) -> None:
        self._fact_store = fact_store
        self._belief_store = belief_store

    def build_context(self, character: Character, tick: int) -> CharacterKnowledgeContext:
        visible_facts = self._fact_store.list_visible_for(character)
        beliefs = self._belief_store.list_for_character(character.id)
        facts = tuple(self._fact_entry(fact) for fact in visible_facts)
        clues = self._build_clues(beliefs, visible_facts)
        audit_log = self._build_audit_log(character, visible_facts, beliefs, clues)
        return CharacterKnowledgeContext(
            character_id=character.id,
            tick=tick,
            facts=facts,
            clues=clues,
            audit_log=audit_log,
        )

    def plan_diffusion(
        self,
        belief: Belief,
        target_character_id: str,
        delay_ticks: int,
    ) -> PropagationTask:
        if delay_ticks < 0:
            raise ValueError("delay_ticks must be >= 0")
        return PropagationTask(
            belief_id=belief.belief_id,
            origin_character_id=belief.character_id,
            target_character_id=target_character_id,
            available_at_tick=belief.acquired_tick + delay_ticks,
        )

    def _build_clues(
        self,
        beliefs: tuple[Belief, ...],
        visible_facts: tuple[Fact, ...],
    ) -> tuple[KnowledgeEntry, ...]:
        visible_fact_ids = {fact.id for fact in visible_facts}
        clues = []
        for belief in beliefs:
            if belief.fact_id is not None and belief.fact_id in visible_fact_ids:
                continue
            clues.append(
                KnowledgeEntry(
                    entry_id=belief.belief_id,
                    entry_type="clue",
                    content=belief.summary,
                    confidence=belief.confidence,
                    source_refs=self._belief_refs(belief),
                )
            )
        return tuple(clues)

    def _build_audit_log(
        self,
        character: Character,
        visible_facts: tuple[Fact, ...],
        beliefs: tuple[Belief, ...],
        clues: tuple[KnowledgeEntry, ...],
    ) -> tuple[str, ...]:
        fact_ids = ",".join(fact.id for fact in visible_facts) or "-"
        belief_ids = ",".join(belief.belief_id for belief in beliefs) or "-"
        clue_ids = ",".join(clue.entry_id for clue in clues) or "-"
        return (
            f"character={character.id}",
            f"location={character.location_id}",
            f"visible_facts={fact_ids}",
            f"beliefs={belief_ids}",
            f"clues={clue_ids}",
        )

    @staticmethod
    def _fact_entry(fact: Fact) -> KnowledgeEntry:
        refs = (fact.id,) if fact.source_event_id is None else (fact.id, fact.source_event_id)
        return KnowledgeEntry(
            entry_id=fact.id,
            entry_type="fact",
            content=fact.content,
            confidence=1.0,
            source_refs=refs,
        )

    @staticmethod
    def _belief_refs(belief: Belief) -> tuple[str, ...]:
        if belief.fact_id is None:
            return (belief.source_type,)
        return (belief.source_type, belief.fact_id)
