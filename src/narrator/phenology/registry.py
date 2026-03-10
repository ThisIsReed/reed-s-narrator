"""Registry for phenology hard-constraint rules."""

from __future__ import annotations

from typing import Protocol

from narrator.core.rule_engine import RuleExecutionRecord
from narrator.models import StateChange, WorldState
from narrator.phenology.calendar import PhenologySnapshot


class PhenologyRule(Protocol):
    name: str
    priority: int

    def match(self, world: WorldState, snapshot: PhenologySnapshot) -> bool:
        ...

    def apply(self, world: WorldState, snapshot: PhenologySnapshot) -> tuple[StateChange, ...]:
        ...


class PhenologyRegistry:
    """Execute phenology rules in stable order."""

    def __init__(self) -> None:
        self._rules: list[PhenologyRule] = []

    def register(self, rule: PhenologyRule) -> None:
        if not getattr(rule, "name", ""):
            raise ValueError("rule.name must not be empty")
        self._rules.append(rule)

    def evaluate(
        self,
        world: WorldState,
        snapshot: PhenologySnapshot,
    ) -> tuple[tuple[StateChange, ...], tuple[RuleExecutionRecord, ...]]:
        state_changes: list[StateChange] = []
        audit_log: list[RuleExecutionRecord] = []
        for _, rule in self._sorted_rules():
            matched = rule.match(world, snapshot)
            changes = rule.apply(world, snapshot) if matched else ()
            state_changes.extend(changes)
            audit_log.append(
                RuleExecutionRecord(
                    rule_name=rule.name,
                    priority=rule.priority,
                    matched=matched,
                    state_change_count=len(changes),
                )
            )
        return tuple(state_changes), tuple(audit_log)

    def _sorted_rules(self) -> list[tuple[int, PhenologyRule]]:
        indexed_rules = list(enumerate(self._rules))
        return sorted(indexed_rules, key=lambda item: (item[1].priority, item[0]))
