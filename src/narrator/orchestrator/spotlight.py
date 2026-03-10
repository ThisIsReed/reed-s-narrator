"""Spotlight assignment for ACTIVE/PASSIVE/DORMANT execution."""

from __future__ import annotations

from random import Random

from narrator.config import SpotlightConfig
from narrator.models import Character, Event, StateMode
from narrator.models.base import DomainModel

MODE_PRIORITY = {
    StateMode.ACTIVE: 0,
    StateMode.PASSIVE: 1,
    StateMode.DORMANT: 2,
}
BASE_AVAILABILITY_SCORE = 1.0
LONG_ACTION_AVAILABILITY_SCORE = 0.2


class SpotlightEntry(DomainModel):
    character_id: str
    state_mode: StateMode
    score: float
    reasons: tuple[str, ...]


class SpotlightAssignments(DomainModel):
    active_ids: tuple[str, ...] = ()
    passive_ids: tuple[str, ...] = ()
    dormant_ids: tuple[str, ...] = ()
    entries: tuple[SpotlightEntry, ...] = ()


class SpotlightDirector:
    def __init__(self, config: SpotlightConfig) -> None:
        self._config = config
        self._weight_sum = _weight_sum(config)

    def assign(
        self,
        characters: dict[str, Character],
        events: tuple[Event, ...],
        rng: Random,
    ) -> SpotlightAssignments:
        impact = _extract_event_impact(events)
        entries = tuple(
            _classify_character(character, impact, self._config, self._weight_sum, rng)
            for _, character in sorted(characters.items())
        )
        ordered = tuple(sorted(entries, key=_entry_sort_key))
        return SpotlightAssignments(
            active_ids=_ids_for_mode(ordered, StateMode.ACTIVE),
            passive_ids=_ids_for_mode(ordered, StateMode.PASSIVE),
            dormant_ids=_ids_for_mode(ordered, StateMode.DORMANT),
            entries=ordered,
        )


def _classify_character(
    character: Character,
    impact: "_ImpactSummary",
    config: SpotlightConfig,
    weight_sum: float,
    rng: Random,
) -> SpotlightEntry:
    relation = 1.0 if character.id in impact.character_ids else 0.0
    geo = 1.0 if character.location_id in impact.location_ids else 0.0
    availability = _availability_score(character)
    noise = rng.random()
    score = _weighted_score(character, geo, relation, availability, noise, config, weight_sum)
    mode, reasons = _resolve_mode(character, relation, geo, score, config)
    return SpotlightEntry(
        character_id=character.id,
        state_mode=mode,
        score=round(score, 6),
        reasons=reasons + (_score_reason(geo, relation, availability, noise),),
    )


def _resolve_mode(
    character: Character,
    relation: float,
    geo: float,
    score: float,
    config: SpotlightConfig,
) -> tuple[StateMode, tuple[str, ...]]:
    if relation > 0.0:
        return StateMode.ACTIVE, ("forced ACTIVE by direct event impact",)
    if geo > 0.0:
        return StateMode.PASSIVE, ("forced PASSIVE by co-located event impact",)
    if score >= config.threshold_active:
        return StateMode.ACTIVE, ("score >= threshold_active",)
    if score >= config.threshold_passive:
        return StateMode.PASSIVE, ("score >= threshold_passive",)
    return StateMode.DORMANT, ("score < threshold_passive",)


def _weighted_score(
    character: Character,
    geo: float,
    relation: float,
    availability: float,
    noise: float,
    config: SpotlightConfig,
    weight_sum: float,
) -> float:
    weights = config.weights
    weighted_total = (
        weights.geo * geo
        + weights.relation * relation
        + weights.availability * availability
        + weights.narrative_importance * character.narrative_importance
        + weights.random_noise * noise
    )
    return weighted_total / weight_sum


def _availability_score(character: Character) -> float:
    if character.long_action is None:
        return BASE_AVAILABILITY_SCORE
    return LONG_ACTION_AVAILABILITY_SCORE


def _weight_sum(config: SpotlightConfig) -> float:
    weights = config.weights
    total = (
        weights.geo
        + weights.relation
        + weights.availability
        + weights.narrative_importance
        + weights.random_noise
    )
    if total <= 0.0:
        raise ValueError("spotlight weights sum must be > 0")
    return total


def _ids_for_mode(entries: tuple[SpotlightEntry, ...], mode: StateMode) -> tuple[str, ...]:
    return tuple(entry.character_id for entry in entries if entry.state_mode is mode)


def _entry_sort_key(entry: SpotlightEntry) -> tuple[int, float, str]:
    return (MODE_PRIORITY[entry.state_mode], -entry.score, entry.character_id)


def _score_reason(geo: float, relation: float, availability: float, noise: float) -> str:
    return (
        "geo={geo:.2f},relation={relation:.2f},availability={availability:.2f},"
        "noise={noise:.2f}"
    ).format(
        geo=geo,
        relation=relation,
        availability=availability,
        noise=noise,
    )


class _ImpactSummary(DomainModel):
    location_ids: tuple[str, ...] = ()
    character_ids: tuple[str, ...] = ()


def _extract_event_impact(events: tuple[Event, ...]) -> _ImpactSummary:
    location_ids: set[str] = set()
    character_ids: set[str] = set()
    for event in events:
        location_ids.update(_tuple_scope_values(event.impact_scope, "location_ids", "location_id"))
        character_ids.update(
            _tuple_scope_values(event.impact_scope, "character_ids", "character_id")
        )
        character_ids.update(
            _tuple_scope_values(
                event.impact_scope,
                "target_character_ids",
                "target_character_id",
            )
        )
    return _ImpactSummary(
        location_ids=tuple(sorted(location_ids)),
        character_ids=tuple(sorted(character_ids)),
    )


def _tuple_scope_values(
    scope: dict[str, object],
    plural_key: str,
    single_key: str,
) -> tuple[str, ...]:
    values = scope.get(plural_key)
    if isinstance(values, list | tuple):
        return tuple(str(item) for item in values)
    value = scope.get(single_key)
    if value is None:
        return ()
    return (str(value),)
