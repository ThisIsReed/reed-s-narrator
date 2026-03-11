from __future__ import annotations

from narrator.core import RuleContext, RuleEngine, UnresolvedEventPressureRule
from narrator.models import Action, ActionResult, Character, Granularity, StateMode, Verdict, WorldState
from narrator.models.event import Event
from narrator.orchestrator.event_pool import EventPoolSnapshot
from narrator.orchestrator.granularity import GranularityDecision
from narrator.orchestrator.spotlight import SpotlightAssignments, SpotlightEntry
from narrator.orchestrator.tick_helpers import apply_world_rules_stage


class StaticRule:
    name = "static"
    priority = 1

    def match(self, world: WorldState, context: RuleContext) -> bool:
        return True

    def apply(self, world: WorldState, context: RuleContext):
        return ()


def test_apply_world_rules_stage_projects_state_changes_and_audit() -> None:
    world = _build_world()
    engine = RuleEngine()
    engine.register(UnresolvedEventPressureRule())
    event_snapshot = EventPoolSnapshot(
        active_events=(world.events["alarm-1"],),
        new_events=(),
    )
    assignments = _assignments()
    action_results = (
        ActionResult(
            action=Action(character_id="hero", action_type="investigate", source_event_id="alarm-1"),
            verdict=Verdict.APPROVED,
        ),
    )

    updated, stage = apply_world_rules_stage(
        world,
        tick=1,
        granularity=GranularityDecision(granularity=Granularity.DAY, reason="stable", instant_rounds=0),
        event_snapshot=event_snapshot,
        assignments=assignments,
        action_results=action_results,
        rule_engine=engine,
    )

    assert updated.resources["unresolved_event_pressure"] == 1.0
    assert stage.stage == "world_rules"
    assert stage.audit_log == ("unresolved_event_pressure:matched:1",)
    assert stage.state_changes[0].path == "resources.unresolved_event_pressure"
    assert stage.artifact_ids == ("unresolved_event_pressure",)


def test_apply_world_rules_stage_keeps_empty_stage_for_unmatched_rules() -> None:
    world = _build_world(resources={"unresolved_event_pressure": 1.0})
    engine = RuleEngine()
    engine.register(StaticRule())
    event_snapshot = EventPoolSnapshot(
        active_events=(world.events["alarm-1"],),
        new_events=(),
    )

    updated, stage = apply_world_rules_stage(
        world,
        tick=1,
        granularity=GranularityDecision(granularity=Granularity.DAY, reason="stable", instant_rounds=0),
        event_snapshot=event_snapshot,
        assignments=_assignments(),
        action_results=(),
        rule_engine=engine,
    )

    assert updated == world
    assert stage.stage == "world_rules"
    assert stage.audit_log == ("static:matched:0",)
    assert stage.state_changes == ()
    assert stage.artifact_ids == ("static",)


def test_unresolved_event_pressure_rule_is_deterministic() -> None:
    engine = RuleEngine()
    engine.register(UnresolvedEventPressureRule())
    world = _build_world()
    context = RuleContext(tick=1, seed=13)

    assert engine.settle(world, context) == engine.settle(world, context)


def _build_world(resources: dict[str, float] | None = None) -> WorldState:
    return WorldState(
        tick=1,
        seed=13,
        granularity=Granularity.DAY,
        characters={
            "hero": Character(
                id="hero",
                name="Hero",
                state_mode=StateMode.ACTIVE,
                location_id="town",
            )
        },
        events={
            "alarm-1": Event(
                id="alarm-1",
                tick_created=1,
                impact_scope={"location_id": "town", "target_character_id": "hero"},
            )
        },
        resources=resources or {},
    )


def _assignments() -> SpotlightAssignments:
    return SpotlightAssignments(
        entries=(
            SpotlightEntry(
                character_id="hero",
                score=1.0,
                state_mode=StateMode.ACTIVE,
                reasons=("targeted event",),
            ),
        )
    )
