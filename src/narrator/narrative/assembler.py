"""Narrative source assembly and deterministic beat selection."""

from __future__ import annotations

from pathlib import Path

from narrator.models import ActionResult, StateChange
from narrator.persistence import ActionLogRepository, SQLiteDatabase, TickAuditRepository
from narrator.replay import ReplayRecord, ReplaySource, list_ticks, load_record

from .models import NarrativeBeat, NarrativeSourceTick

MAX_RESOURCE_CHANGES = 3


class NarrativeAssembler:
    def __init__(self, db_path: str | Path, source: ReplaySource = "snapshot") -> None:
        self._db_path = Path(db_path)
        self._source = source
        if not self._db_path.exists():
            raise FileNotFoundError(f"database not found: {self._db_path}")
        self._ticks = list_ticks(self._db_path, source)

    @property
    def source(self) -> ReplaySource:
        return self._source

    @property
    def ticks(self) -> tuple[int, ...]:
        return self._ticks

    def assemble_tick(self, tick: int) -> NarrativeSourceTick:
        current = load_record(self._db_path, self._source, tick)
        previous = self._previous_record(tick)
        actions, audit = self._load_tick_artifacts(tick)
        state_changes = _world_changes(previous, current)
        active_ids = tuple(audit["action_character_ids"]) or tuple(
            result.action.character_id for result in actions
        )
        event_ids = tuple(sorted(current.world.events))
        unresolved = tuple(
            event_id for event_id, event in sorted(current.world.events.items()) if not event.resolved
        )
        source_refs = (
            f"{self._source}:{tick}",
            f"action_log:{tick}",
            f"tick_audit:{tick}",
        )
        return NarrativeSourceTick(
            tick=tick,
            source=self._source,
            granularity=current.world.granularity.value,
            event_ids=event_ids,
            active_character_ids=active_ids,
            action_results=actions,
            state_changes=state_changes,
            phenology_summary=_phenology_summary(current),
            knowledge_summary=_knowledge_summary(current, previous),
            unresolved_event_ids=unresolved,
            source_refs=source_refs,
        )

    def build_beat(self, tick: int) -> NarrativeBeat:
        source_tick = self.assemble_tick(tick)
        return _build_beat(source_tick)

    def list_range(self, start_tick: int, end_tick: int) -> tuple[int, ...]:
        if start_tick > end_tick:
            raise ValueError("from-tick must be less than or equal to to-tick")
        selected = tuple(tick for tick in self._ticks if start_tick <= tick <= end_tick)
        if not selected:
            raise LookupError(f"no ticks found between {start_tick} and {end_tick}")
        return selected

    def _previous_record(self, tick: int) -> ReplayRecord | None:
        previous_ticks = tuple(item for item in self._ticks if item < tick)
        if not previous_ticks:
            return None
        return load_record(self._db_path, self._source, previous_ticks[-1])

    def _load_tick_artifacts(self, tick: int) -> tuple[tuple[ActionResult, ...], dict[str, object]]:
        database = SQLiteDatabase(self._db_path)
        connection = database.connect()
        try:
            actions = ActionLogRepository(connection).list_by_tick(tick)
            audit = TickAuditRepository(connection).load(tick)
        finally:
            connection.close()
        return actions, audit


def _build_beat(source_tick: NarrativeSourceTick) -> NarrativeBeat:
    background = _background_line(source_tick)
    action = _action_line(source_tick)
    result = _result_line(source_tick)
    outlook = _outlook_line(source_tick)
    priority = _priority(source_tick)
    character_ids = tuple(sorted({item.action.character_id for item in source_tick.action_results}))
    event_ids = tuple(sorted(set(source_tick.event_ids)))
    return NarrativeBeat(
        tick=source_tick.tick,
        title=f"第 {source_tick.tick} 回合",
        priority=priority,
        background=background,
        action=action,
        result=result,
        outlook=outlook,
        mentioned_character_ids=character_ids,
        mentioned_event_ids=event_ids,
        source_refs=source_tick.source_refs,
    )


def _priority(source_tick: NarrativeSourceTick) -> str:
    if _new_or_resolved_events(source_tick.state_changes):
        return "event"
    if source_tick.action_results:
        return "action"
    if _world_change_lines(source_tick.state_changes):
        return "world"
    if "pending" in source_tick.knowledge_summary:
        return "knowledge"
    return "quiet"


def _background_line(source_tick: NarrativeSourceTick) -> str:
    events = _new_or_resolved_events(source_tick.state_changes)
    if events:
        return f"背景推进：{'; '.join(events)}。"
    return f"背景推进：时间粒度为 {source_tick.granularity}，{source_tick.phenology_summary}。"


def _action_line(source_tick: NarrativeSourceTick) -> str:
    if not source_tick.action_results:
        return "关键行动：本回合没有角色进入主动行动。"
    rendered = []
    for result in source_tick.action_results:
        if result.flavor_text:
            rendered.append(f"{result.action.character_id}：{result.flavor_text}")
            continue
        rendered.append(
            f"{result.action.character_id} 执行 {result.action.action_type}"
        )
    return f"关键行动：{'; '.join(rendered)}。"


def _result_line(source_tick: NarrativeSourceTick) -> str:
    parts = _world_change_lines(source_tick.state_changes)
    if not parts:
        parts = [source_tick.knowledge_summary]
    return f"结果变化：{'; '.join(parts)}。"


def _outlook_line(source_tick: NarrativeSourceTick) -> str:
    if source_tick.unresolved_event_ids:
        pending = ", ".join(source_tick.unresolved_event_ids)
        return f"未完事项：仍有事件待收束，{pending} 尚未解决。"
    return "未完事项：本回合主要矛盾已暂时收束。"


def _new_or_resolved_events(state_changes: tuple[StateChange, ...]) -> tuple[str, ...]:
    lines = []
    for change in state_changes:
        if not change.path.startswith("events."):
            continue
        parts = change.path.split(".")
        event_id = parts[1]
        if parts[-1] == "resolved" and change.after is True:
            lines.append(f"事件 {event_id} 被处理")
            continue
        if change.before is None:
            lines.append(f"新事件 {event_id} 进入舞台")
    return tuple(dict.fromkeys(lines))


def _world_change_lines(state_changes: tuple[StateChange, ...]) -> list[str]:
    changes: list[str] = []
    resource_changes = 0
    for change in state_changes:
        if change.path.startswith("resources.") and resource_changes < MAX_RESOURCE_CHANGES:
            resource_name = change.path.split(".", 1)[1]
            changes.append(f"{resource_name} 从 {change.before} 变为 {change.after}")
            resource_changes += 1
            continue
        if change.path.startswith("flags."):
            flag_name = change.path.split(".", 1)[1]
            changes.append(f"标记 {flag_name} 更新为 {change.after}")
            continue
        if change.path.startswith("phenology."):
            label = change.path.split(".", 1)[1]
            changes.append(f"{label} 更新为 {change.after}")
    return changes


def _phenology_summary(record: ReplayRecord) -> str:
    phenology = record.world.phenology
    festivals = ",".join(phenology.festivals) or "无节庆"
    return (
        f"时序来到第 {phenology.day_of_year} 日，季节为 {phenology.season}，"
        f"气候为 {phenology.climate}，节庆为 {festivals}"
    )


def _knowledge_summary(current: ReplayRecord, previous: ReplayRecord | None) -> str:
    current_pending = len(current.world.pending_propagation)
    if previous is None:
        return f"知识传播待处理任务数为 {current_pending}"
    previous_pending = len(previous.world.pending_propagation)
    if current_pending == previous_pending:
        return f"知识传播待处理任务数维持在 {current_pending}"
    return f"知识传播待处理任务数从 {previous_pending} 变为 {current_pending}"


def _world_changes(
    previous: ReplayRecord | None,
    current: ReplayRecord,
) -> tuple[StateChange, ...]:
    if previous is None:
        return _bootstrap_changes(current)
    changes = []
    changes.extend(_mapping_changes("events", previous.world.events, current.world.events))
    changes.extend(_mapping_changes("resources", previous.world.resources, current.world.resources))
    changes.extend(_mapping_changes("flags", previous.world.flags, current.world.flags))
    changes.extend(_mapping_changes("phenology", previous.world.phenology.model_dump(mode="json"), current.world.phenology.model_dump(mode="json")))
    return tuple(changes)


def _bootstrap_changes(current: ReplayRecord) -> tuple[StateChange, ...]:
    changes = []
    for event_id, event in sorted(current.world.events.items()):
        changes.append(
            StateChange(
                path=f"events.{event_id}",
                before=None,
                after=event.model_dump(mode="json"),
                reason="bootstrap event state",
            )
        )
    for key, value in sorted(current.world.resources.items()):
        changes.append(
            StateChange(
                path=f"resources.{key}",
                before=None,
                after=value,
                reason="bootstrap resource state",
            )
        )
    return tuple(changes)


def _mapping_changes(prefix: str, previous: object, current: object) -> list[StateChange]:
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return []
    changes = []
    keys = tuple(sorted(set(previous) | set(current)))
    for key in keys:
        before = previous.get(key)
        after = current.get(key)
        if before == after:
            continue
        if prefix == "events" and isinstance(before, dict) and isinstance(after, dict):
            if before.get("resolved") != after.get("resolved"):
                changes.append(
                    StateChange(
                        path=f"events.{key}.resolved",
                        before=before.get("resolved"),
                        after=after.get("resolved"),
                        reason="event resolution changed",
                    )
                )
                continue
        changes.append(
            StateChange(
                path=f"{prefix}.{key}",
                before=before,
                after=after,
                reason=f"{prefix} changed",
            )
        )
    return changes
