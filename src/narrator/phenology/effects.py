"""Phenology effects and world-state application."""

from __future__ import annotations

from narrator.core.rule_engine import RuleExecutionRecord
from narrator.models.base import DomainModel
from narrator.models import StateChange, WorldState
from narrator.phenology.calendar import PhenologyCalendar, PhenologySnapshot
from narrator.phenology.registry import PhenologyRegistry

WINTER_MARCH_PENALTY = 15.0
RAINY_DISEASE_INCREASE = 10.0
POOR_HARVEST_GRAIN_LOSS = 20.0


class PhenologyUpdateResult(DomainModel):
    world: WorldState
    snapshot: PhenologySnapshot
    state_changes: tuple[StateChange, ...]
    audit_log: tuple[RuleExecutionRecord, ...]


class WinterMarchPenaltyRule:
    name = "winter_march_penalty"
    priority = 10

    def match(self, world: WorldState, snapshot: PhenologySnapshot) -> bool:
        return snapshot.season == "winter" and any(
            character.long_action == "march" for character in world.characters.values()
        )

    def apply(self, world: WorldState, snapshot: PhenologySnapshot) -> tuple[StateChange, ...]:
        return (_resource_change(world, "military_readiness", -WINTER_MARCH_PENALTY, self.name),)


class RainyDiseasePressureRule:
    name = "rainy_disease_pressure"
    priority = 20

    def match(self, world: WorldState, snapshot: PhenologySnapshot) -> bool:
        return snapshot.climate == "rainy"

    def apply(self, world: WorldState, snapshot: PhenologySnapshot) -> tuple[StateChange, ...]:
        return (_resource_change(world, "disease_pressure", RAINY_DISEASE_INCREASE, self.name),)


class PoorHarvestGrainRule:
    name = "poor_harvest_grain_drop"
    priority = 30

    def match(self, world: WorldState, snapshot: PhenologySnapshot) -> bool:
        return snapshot.season == "autumn" and world.flags.get("poor_harvest", False)

    def apply(self, world: WorldState, snapshot: PhenologySnapshot) -> tuple[StateChange, ...]:
        return (_resource_change(world, "grain_stock", -POOR_HARVEST_GRAIN_LOSS, self.name),)


def build_default_registry() -> PhenologyRegistry:
    registry = PhenologyRegistry()
    registry.register(WinterMarchPenaltyRule())
    registry.register(RainyDiseasePressureRule())
    registry.register(PoorHarvestGrainRule())
    return registry


def apply_phenology(
    world: WorldState,
    tick: int,
    calendar: PhenologyCalendar | None = None,
    registry: PhenologyRegistry | None = None,
) -> PhenologyUpdateResult:
    active_calendar = calendar or PhenologyCalendar()
    active_registry = registry or build_default_registry()
    snapshot = active_calendar.snapshot_for_tick(tick)
    changes, audit_log = active_registry.evaluate(world, snapshot)
    baseline_change = _phenology_state_change(world, snapshot)
    updated_world = _apply_changes(world, (baseline_change, *changes), snapshot)
    return PhenologyUpdateResult(
        world=updated_world,
        snapshot=snapshot,
        state_changes=(baseline_change, *changes),
        audit_log=audit_log,
    )


def _resource_change(world: WorldState, key: str, delta: float, reason: str) -> StateChange:
    before = world.resources.get(key, 0.0)
    return StateChange(path=f"resources.{key}", before=before, after=before + delta, reason=reason)


def _phenology_state_change(world: WorldState, snapshot: PhenologySnapshot) -> StateChange:
    before = world.phenology.day_of_year
    after = snapshot.day_of_year
    return StateChange(
        path="phenology.day_of_year",
        before=before,
        after=after,
        reason="phenology_calendar_tick",
    )


def _apply_changes(
    world: WorldState,
    changes: tuple[StateChange, ...],
    snapshot: PhenologySnapshot,
) -> WorldState:
    resources = dict(world.resources)
    for change in changes:
        if change.path.startswith("resources."):
            resources[change.path.split(".", 1)[1]] = float(change.after)
    return world.model_copy(
        update={
            "tick": snapshot.tick,
            "resources": resources,
            "phenology": snapshot.to_state(),
        }
    )
