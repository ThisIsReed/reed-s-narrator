"""Deterministic rule engine with stable execution ordering and audit."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field

from narrator.models.action import Action, StateChange
from narrator.models.base import DomainModel
from narrator.models.world import WorldState


class RuleContext(DomainModel):
    tick: int = Field(..., ge=0)
    seed: int
    action: Action | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuleExecutionRecord(DomainModel):
    rule_name: str = Field(..., min_length=1)
    priority: int
    matched: bool
    state_change_count: int = Field(..., ge=0)


class RuleEngineResult(DomainModel):
    state_changes: tuple[StateChange, ...] = ()
    audit_log: tuple[RuleExecutionRecord, ...] = ()


class Rule(Protocol):
    name: str
    priority: int

    def match(self, world: WorldState, context: RuleContext) -> bool:
        ...

    def apply(self, world: WorldState, context: RuleContext) -> tuple[StateChange, ...]:
        ...


class RuleEngine:
    """Execute rules in deterministic order and emit full audit trace."""

    def __init__(self) -> None:
        self._rules: list[Rule] = []

    def register(self, rule: Rule) -> None:
        if not getattr(rule, "name", ""):
            raise ValueError("rule.name must not be empty")
        self._rules.append(rule)

    def settle(self, world: WorldState, context: RuleContext) -> RuleEngineResult:
        state_changes: list[StateChange] = []
        audit_log: list[RuleExecutionRecord] = []
        for _, rule in self._sorted_rules():
            matched = rule.match(world, context)
            changes = rule.apply(world, context) if matched else ()
            state_changes.extend(changes)
            audit_log.append(
                RuleExecutionRecord(
                    rule_name=rule.name,
                    priority=rule.priority,
                    matched=matched,
                    state_change_count=len(changes),
                )
            )
        return RuleEngineResult(state_changes=tuple(state_changes), audit_log=tuple(audit_log))

    def _sorted_rules(self) -> list[tuple[int, Rule]]:
        indexed_rules = list(enumerate(self._rules))
        return sorted(indexed_rules, key=lambda item: (item[1].priority, item[0]))
