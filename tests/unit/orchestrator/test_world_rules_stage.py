from __future__ import annotations

from narrator.core import (
    InterruptSignal,
    RuleContext,
    RuleEngine,
    UnresolvedEventPressureRule,
    build_default_rule_engine,
)
from narrator.models import (
    Action,
    ActionResult,
    Character,
    Granularity,
    LongActionState,
    LongActionStatus,
    StateMode,
    Verdict,
    WorldState,
)
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
        interrupt_signals=(),
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
        interrupt_signals=(),
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


def test_apply_world_rules_stage_pauses_long_action_when_interrupt_present() -> None:
    world = _build_world(
        long_action=LongActionState(action_type="march", started_tick=0, remaining_ticks=3)
    )

    updated, stage = apply_world_rules_stage(
        world,
        tick=1,
        granularity=GranularityDecision(granularity=Granularity.DAY, reason="stable", instant_rounds=0),
        event_snapshot=EventPoolSnapshot(active_events=(world.events["alarm-1"],), new_events=()),
        assignments=_assignments(),
        action_results=(),
        interrupt_signals=(
            InterruptSignal(
                character_id="hero",
                reason="targeted_event_interrupt",
                tick=1,
                metadata={"event_id": "alarm-1"},
            ),
        ),
        rule_engine=build_default_rule_engine(),
    )

    long_action = updated.characters["hero"].long_action
    assert long_action is not None
    assert long_action.status is LongActionStatus.PAUSED
    assert long_action.pause_reason == "targeted_event_interrupt"
    assert long_action.interrupt_history[0].event_id == "alarm-1"
    assert stage.audit_log[:3] == (
        "long_action_interrupt:matched:1",
        "long_action_resume:skipped:0",
        "long_action_progress:skipped:0",
    )


def test_apply_world_rules_stage_resumes_and_progresses_paused_long_action() -> None:
    paused_action = LongActionState(
        action_type="march",
        started_tick=0,
        remaining_ticks=3,
        status=LongActionStatus.PAUSED,
        pause_reason="targeted_event_interrupt",
    )
    world = _build_world(long_action=paused_action)
    resolved_event = world.events["alarm-1"].model_copy(update={"resolved": True})
    world = world.model_copy(update={"events": {"alarm-1": resolved_event}})

    updated, stage = apply_world_rules_stage(
        world,
        tick=2,
        granularity=GranularityDecision(granularity=Granularity.DAY, reason="stable", instant_rounds=0),
        event_snapshot=EventPoolSnapshot(new_events=(), active_events=()),
        assignments=_assignments(),
        action_results=(),
        interrupt_signals=(),
        rule_engine=build_default_rule_engine(),
    )

    long_action = updated.characters["hero"].long_action
    assert long_action is not None
    assert long_action.status is LongActionStatus.IN_PROGRESS
    assert long_action.remaining_ticks == 2
    assert long_action.last_progress_tick == 2
    assert stage.audit_log[:3] == (
        "long_action_interrupt:skipped:0",
        "long_action_resume:matched:1",
        "long_action_progress:matched:1",
    )


def test_apply_world_rules_stage_keeps_long_action_paused_while_targeted_event_unresolved() -> None:
    paused_action = LongActionState(
        action_type="march",
        started_tick=0,
        remaining_ticks=3,
        status=LongActionStatus.PAUSED,
        pause_reason="targeted_event_interrupt",
    )
    world = _build_world(long_action=paused_action)

    updated, stage = apply_world_rules_stage(
        world,
        tick=2,
        granularity=GranularityDecision(granularity=Granularity.DAY, reason="stable", instant_rounds=0),
        event_snapshot=EventPoolSnapshot(active_events=(world.events["alarm-1"],), new_events=()),
        assignments=_assignments(),
        action_results=(),
        interrupt_signals=(),
        rule_engine=build_default_rule_engine(),
    )

    long_action = updated.characters["hero"].long_action
    assert long_action is not None
    assert long_action.status is LongActionStatus.PAUSED
    assert long_action.remaining_ticks == 3
    assert stage.audit_log[:3] == (
        "long_action_interrupt:skipped:0",
        "long_action_resume:skipped:0",
        "long_action_progress:skipped:0",
    )


def _build_world(
    resources: dict[str, float] | None = None,
    long_action: LongActionState | None = None,
) -> WorldState:
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
                long_action=long_action,
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
