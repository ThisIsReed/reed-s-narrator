"""Helpers for runtime knowledge mutation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from narrator.knowledge.belief_store import Belief
from narrator.knowledge.fact_store import Fact, FactVisibility
from narrator.models.action import ActionResult
from narrator.models.character import Character
from narrator.models.event import Event
from narrator.models.knowledge import PropagationTask

if TYPE_CHECKING:
    from narrator.models.world import WorldState


def merge_facts(
    existing: dict[str, dict[str, Any]],
    facts: tuple[Fact, ...],
) -> dict[str, dict[str, Any]]:
    updated = dict(existing)
    for fact in facts:
        updated[fact.id] = fact.model_dump(mode="json")
    return updated


def merge_beliefs(
    existing: dict[str, tuple[dict[str, Any], ...]],
    beliefs: tuple[Belief, ...],
) -> dict[str, tuple[dict[str, Any], ...]]:
    updated = dict(existing)
    for belief in beliefs:
        ordered = [
            item
            for item in updated.get(belief.character_id, ())
            if item["belief_id"] != belief.belief_id
        ]
        ordered.append(belief.model_dump(mode="json"))
        updated[belief.character_id] = tuple(sorted(ordered, key=lambda item: item["belief_id"]))
    return updated


def split_pending_tasks(
    tasks: tuple[PropagationTask, ...],
    tick: int,
) -> tuple[tuple[PropagationTask, ...], tuple[PropagationTask, ...]]:
    ready = tuple(task for task in tasks if task.available_at_tick <= tick)
    pending = tuple(task for task in tasks if task.available_at_tick > tick)
    return ready, pending


def peer_character_ids(world: WorldState, origin: Character) -> tuple[str, ...]:
    peers = [
        character.id
        for character in world.characters.values()
        if character.id != origin.id and character.location_id == origin.location_id
    ]
    return tuple(sorted(peers))


def event_visibility(event: Event) -> FactVisibility:
    location_id = event.impact_scope.get("location_id")
    if isinstance(location_id, str) and location_id:
        return FactVisibility(scope="location", location_ids=(location_id,))
    target_id = event.impact_scope.get("target_character_id")
    if isinstance(target_id, str) and target_id:
        return FactVisibility(scope="private", character_ids=(target_id,))
    return FactVisibility()


def event_content(event: Event) -> str:
    details = event.soft_prompts or event.hard_effects or event.tags
    detail = details[0] if details else event.id
    return f"{event.id}:{detail}"


def direct_belief(result: ActionResult, tick: int) -> Belief:
    source_event_id = result.action.source_event_id
    fact_id = None if source_event_id is None else f"event:{source_event_id}"
    return Belief(
        character_id=result.action.character_id,
        belief_id=f"action:{tick}:{result.action.character_id}",
        summary=belief_summary(result),
        acquired_tick=tick,
        fact_id=fact_id,
        confidence=1.0,
        source_type="direct",
    )


def belief_summary(result: ActionResult) -> str:
    verdict = result.verdict.value.lower()
    return f"{result.action.character_id}:{result.action.action_type}:{verdict}"


def task_id(belief: Belief, target_character_id: str, delay_ticks: int) -> str:
    available_at_tick = belief.acquired_tick + delay_ticks
    return f"{belief.belief_id}:{target_character_id}:{available_at_tick}"


def event_audit_log(
    events: tuple[Event, ...],
    facts: tuple[Fact, ...],
) -> tuple[str, ...]:
    event_ids = ",".join(event.id for event in events) or "-"
    fact_ids = ",".join(fact.id for fact in facts) or "-"
    return (f"events={event_ids}", f"event_facts={fact_ids}")


def diffusion_audit_log(
    ready: tuple[PropagationTask, ...],
    pending: tuple[PropagationTask, ...],
) -> tuple[str, ...]:
    ready_ids = ",".join(task.task_id for task in ready) or "-"
    pending_ids = ",".join(task.task_id for task in pending) or "-"
    return (f"diffusion_ready={ready_ids}", f"diffusion_pending={pending_ids}")


def action_audit_log(
    belief: Belief,
    tasks: tuple[PropagationTask, ...],
) -> tuple[str, ...]:
    scheduled_ids = ",".join(task.task_id for task in tasks) or "-"
    return (f"action_belief={belief.belief_id}", f"scheduled_diffusion={scheduled_ids}")
