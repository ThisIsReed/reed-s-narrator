"""Knowledge context building and diffusion planning."""

from __future__ import annotations

from pydantic import Field

from narrator.knowledge.belief_store import Belief, BeliefStore
from narrator.knowledge.fact_store import Fact, FactStore, FactVisibility
from narrator.knowledge.runtime_helpers import (
    action_audit_log,
    direct_belief,
    diffusion_audit_log,
    event_audit_log,
    event_content,
    event_visibility,
    merge_beliefs,
    merge_facts,
    peer_character_ids,
    split_pending_tasks,
    task_id,
)
from narrator.models.action import ActionResult
from narrator.models.character import Character
from narrator.models.event import Event
from narrator.models.knowledge import PropagationTask
from narrator.models.base import DomainModel
from narrator.models.world import WorldState


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


class KnowledgeMutation(DomainModel):
    facts: tuple[Fact, ...] = ()
    beliefs: tuple[Belief, ...] = ()
    pending_tasks: tuple[PropagationTask, ...] = ()
    audit_log: tuple[str, ...] = ()


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

    def load_world_state(self, world: WorldState) -> None:
        for payload in world.facts.values():
            self._fact_store.upsert(Fact.model_validate(payload))
        for belief_group in world.beliefs.values():
            for payload in belief_group:
                self._belief_store.upsert(Belief.model_validate(payload))

    def ingest_events(
        self,
        world: WorldState,
        events: tuple[Event, ...],
        tick: int,
    ) -> tuple[WorldState, KnowledgeMutation]:
        facts = tuple(self._event_fact(event, tick) for event in events)
        for fact in facts:
            self._fact_store.upsert(fact)
        updated_world = world.model_copy(update={"facts": merge_facts(world.facts, facts)})
        return updated_world, KnowledgeMutation(
            facts=facts,
            audit_log=event_audit_log(events, facts),
        )

    def execute_pending(
        self,
        world: WorldState,
        tick: int,
    ) -> tuple[WorldState, KnowledgeMutation]:
        ready, pending = split_pending_tasks(world.pending_propagation, tick)
        beliefs = tuple(self._belief_from_task(task, tick) for task in ready)
        for belief in beliefs:
            self._belief_store.upsert(belief)
        updated_world = world.model_copy(
            update={
                "beliefs": merge_beliefs(world.beliefs, beliefs),
                "pending_propagation": pending,
            }
        )
        return updated_world, KnowledgeMutation(
            beliefs=beliefs,
            pending_tasks=pending,
            audit_log=diffusion_audit_log(ready, pending),
        )

    def capture_action(
        self,
        world: WorldState,
        result: ActionResult,
        tick: int,
    ) -> tuple[WorldState, KnowledgeMutation]:
        belief = direct_belief(result, tick)
        self._belief_store.upsert(belief)
        tasks = self._build_diffusion_tasks(world, belief)
        updated_world = world.model_copy(
            update={
                "beliefs": merge_beliefs(world.beliefs, (belief,)),
                "pending_propagation": (*world.pending_propagation, *tasks),
            }
        )
        return updated_world, KnowledgeMutation(
            beliefs=(belief,),
            pending_tasks=updated_world.pending_propagation,
            audit_log=action_audit_log(belief, tasks),
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
            task_id=task_id(belief, target_character_id, delay_ticks),
            belief_id=belief.belief_id,
            origin_character_id=belief.character_id,
            target_character_id=target_character_id,
            summary=belief.summary,
            available_at_tick=belief.acquired_tick + delay_ticks,
            fact_id=None if belief.source_type == "direct" else belief.fact_id,
            confidence=belief.confidence,
            source_type="rumor" if belief.source_type == "direct" else belief.source_type,
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

    def _build_diffusion_tasks(
        self,
        world: WorldState,
        belief: Belief,
    ) -> tuple[PropagationTask, ...]:
        origin = world.characters[belief.character_id]
        targets = peer_character_ids(world, origin)
        return tuple(self.plan_diffusion(belief, target_id, delay_ticks=1) for target_id in targets)

    @staticmethod
    def _event_fact(event: Event, tick: int) -> Fact:
        visibility = event_visibility(event)
        return Fact(
            id=f"event:{event.id}",
            tick_created=tick,
            content=event_content(event),
            visibility=visibility,
            source_event_id=event.id,
            tags=event.tags,
        )

    @staticmethod
    def _belief_from_task(task: PropagationTask, tick: int) -> Belief:
        return Belief(
            character_id=task.target_character_id,
            belief_id=task.belief_id,
            summary=task.summary,
            acquired_tick=tick,
            fact_id=task.fact_id,
            confidence=task.confidence,
            source_type=task.source_type,
        )
