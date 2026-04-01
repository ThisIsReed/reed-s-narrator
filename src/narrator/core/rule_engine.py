"""Deterministic rule engine with stable execution ordering and audit."""

from __future__ import annotations

from copy import deepcopy
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
        current_world = world
        for _, rule in self._sorted_rules():
            matched = rule.match(current_world, context)
            changes = rule.apply(current_world, context) if matched else ()
            current_world = _apply_state_changes(current_world, changes)
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


def _apply_state_changes(world: WorldState, state_changes: tuple[StateChange, ...]) -> WorldState:
    if not state_changes:
        return world
    payload = world.model_dump(mode="json")
    for change in state_changes:
        _assign_path(payload, change.path.split("."), change.after)
    return WorldState.model_validate(payload)


def _assign_path(payload: dict[str, object], path_parts: list[str], value: object) -> None:
    if not path_parts:
        raise ValueError("state change path must not be empty")
    current: dict[str, object] = payload
    for part in path_parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            raise KeyError(f"state change path not found: {'.'.join(path_parts)}")
        current = next_value
    current[path_parts[-1]] = deepcopy(value)
