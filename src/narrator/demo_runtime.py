"""Deterministic runtime pieces for the local demo."""

from __future__ import annotations

from dataclasses import dataclass

from narrator.agents import RetryOutcome
from narrator.agents.intent import IntentPayload
from narrator.models import Action, ActionResult, Event, StateChange, Verdict, WorldState

ACTION_PLANS = {
    "scout": ("investigate", "tower beacon", "Scout climbs the tower to inspect the beacon."),
    "captain": ("secure", "watchtower gate", "Captain seals the tower gate and questions the guard."),
    "merchant": ("conceal", "tax ledger", "Merchant hides the ledger before inspectors arrive."),
}


@dataclass(frozen=True)
class DemoEventPlan:
    tick: int
    event_id: str
    location_id: str
    target_character_id: str


class DemoEventGenerator:
    def __init__(self, plans: tuple[DemoEventPlan, ...]) -> None:
        self._plans = {plan.tick: plan for plan in plans}

    def generate(self, world: WorldState, tick: int) -> tuple[Event, ...]:
        plan = self._plans.get(tick)
        if plan is None:
            return ()
        return (_build_demo_event(plan),)


class DemoRetryRuntime:
    def __init__(self) -> None:
        self._context_traces: list[str] = []

    @property
    def context_traces(self) -> tuple[str, ...]:
        return tuple(self._context_traces)

    async def execute(self, character, context, settlement_factory) -> RetryOutcome:
        self._context_traces.append(format_context_trace(character.id, context))
        intent = _build_intent(character.id)
        settlement = settlement_factory(intent)
        event_id = active_event_id(settlement.world, character.id)
        result = build_action_result(settlement.world, character.id, event_id)
        return RetryOutcome(result=result, attempts=())


def format_context_trace(character_id: str, context) -> str:
    facts = ",".join(entry.entry_id for entry in context.facts) or "-"
    clues = ",".join(entry.entry_id for entry in context.clues) or "-"
    return f"tick {context.tick} {character_id}: facts={facts} clues={clues}"


def active_event_id(world: WorldState, character_id: str) -> str | None:
    active_events = []
    for event in world.events.values():
        if event.resolved:
            continue
        target_id = event.impact_scope.get("target_character_id")
        if target_id == character_id:
            active_events.append(event)
    if not active_events:
        return None
    ordered = sorted(active_events, key=lambda item: (item.tick_created, item.id))
    return ordered[-1].id


def build_action_result(
    world: WorldState,
    character_id: str,
    event_id: str | None,
) -> ActionResult:
    action_type, focus, flavor_text = _action_plan(character_id)
    action_key = f"{character_id}_actions"
    before = world.resources.get(action_key, 0.0)
    changes = [_resource_change(action_key, before)]
    if event_id is not None:
        changes.append(_resolved_change(event_id))
    return ActionResult(
        action=Action(
            character_id=character_id,
            action_type=action_type,
            parameters={"focus": focus},
            source_event_id=event_id,
            reasoning=f"prioritize {focus}",
        ),
        verdict=Verdict.APPROVED,
        verdict_reason="demo approved",
        state_changes=tuple(changes),
        flavor_text=flavor_text,
    )


def _build_intent(character_id: str) -> IntentPayload:
    action_type, focus, flavor_text = _action_plan(character_id)
    return IntentPayload(
        character_id=character_id,
        action_type=action_type,
        parameters={"focus": focus},
        flavor_text=flavor_text,
    )


def _action_plan(character_id: str) -> tuple[str, str, str]:
    plan = ACTION_PLANS.get(character_id)
    if plan is None:
        raise LookupError(f"demo action plan not found for character: {character_id}")
    return plan


def _build_demo_event(plan: DemoEventPlan) -> Event:
    return Event(
        id=plan.event_id,
        tick_created=plan.tick,
        tags=("granularity:instant",),
        impact_scope={
            "location_id": plan.location_id,
            "target_character_id": plan.target_character_id,
        },
        soft_prompts=(f"demo event for {plan.target_character_id}",),
    )


def _resource_change(action_key: str, before: float) -> StateChange:
    return StateChange(
        path=f"resources.{action_key}",
        before=before,
        after=before + 1.0,
        reason="demo action executed",
    )


def _resolved_change(event_id: str) -> StateChange:
    return StateChange(
        path=f"events.{event_id}.resolved",
        before=False,
        after=True,
        reason="demo event resolved",
    )
