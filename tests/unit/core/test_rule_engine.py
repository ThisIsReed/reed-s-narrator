from __future__ import annotations

from narrator.core.rule_engine import RuleContext, RuleEngine
from narrator.models import Character, Granularity, StateChange, StateMode, WorldState


class StubRule:
    def __init__(
        self,
        name: str,
        priority: int,
        matched: bool,
        changes: tuple[StateChange, ...] = (),
    ) -> None:
        self.name = name
        self.priority = priority
        self._matched = matched
        self._changes = changes

    def match(self, world: WorldState, context: RuleContext) -> bool:
        return self._matched

    def apply(self, world: WorldState, context: RuleContext) -> tuple[StateChange, ...]:
        return self._changes


def _build_world() -> WorldState:
    character = Character(
        id="c-1",
        name="Alice",
        state_mode=StateMode.PASSIVE,
        location_id="loc-1",
    )
    return WorldState(
        tick=5,
        seed=2026,
        granularity=Granularity.DAY,
        characters={"c-1": character},
    )


def _change(rule_name: str, before: int, after: int) -> StateChange:
    return StateChange(
        path=f"resources.{rule_name}",
        before=before,
        after=after,
        reason=rule_name,
    )


def test_rule_engine_orders_by_priority_then_registration() -> None:
    engine = RuleEngine()
    early = StubRule(name="early", priority=5, matched=True, changes=(_change("early", 1, 2),))
    first = StubRule(name="first", priority=1, matched=True, changes=(_change("first", 0, 1),))
    late = StubRule(name="late", priority=5, matched=True, changes=(_change("late", 2, 3),))
    engine.register(early)
    engine.register(first)
    engine.register(late)

    result = engine.settle(_build_world(), RuleContext(tick=6, seed=2026))

    assert [record.rule_name for record in result.audit_log] == ["first", "early", "late"]
    assert [change.reason for change in result.state_changes] == ["first", "early", "late"]


def test_rule_engine_audits_unmatched_rule() -> None:
    engine = RuleEngine()
    engine.register(StubRule(name="noop", priority=0, matched=False))
    result = engine.settle(_build_world(), RuleContext(tick=6, seed=2026))
    assert result.state_changes == ()
    assert result.audit_log[0].matched is False
    assert result.audit_log[0].state_change_count == 0


def test_rule_engine_is_deterministic_for_same_input() -> None:
    engine = RuleEngine()
    engine.register(StubRule(name="stable", priority=1, matched=True, changes=(_change("stable", 3, 4),)))
    world = _build_world()
    context = RuleContext(tick=6, seed=2026)
    assert engine.settle(world, context) == engine.settle(world, context)
