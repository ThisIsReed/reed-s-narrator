"""Replay inspection utilities and CLI entrypoint."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

from narrator.models import WorldState
from narrator.persistence import CheckpointRepository, SQLiteDatabase, WorldSnapshotRepository

MAX_PREVIEW_ITEMS = 10
ReplaySource = Literal["checkpoint", "snapshot"]


@dataclass(frozen=True)
class ReplayRecord:
    source: ReplaySource
    tick: int
    world: WorldState


@dataclass(frozen=True)
class ReplaySummary:
    source: ReplaySource
    tick: int
    granularity: str
    character_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    resource_keys: tuple[str, ...]
    flag_keys: tuple[str, ...]


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "list":
        payload = list_command_data(Path(args.db), args.source)
        _emit_output(payload, _list_command(payload), args.json)
        return 0
    if args.command == "show":
        payload = show_command_data(Path(args.db), args.source, args.tick)
        _emit_output(payload, _show_command(payload), args.json)
        return 0
    payload = diff_command_data(
        Path(args.db),
        args.left_source,
        args.left_tick,
        args.right_source,
        args.right_tick,
    )
    _emit_output(payload, _diff_command(payload), args.json)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect replay checkpoints and snapshots.")
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="List ticks for a source")
    list_parser.add_argument("--source", choices=("checkpoint", "snapshot"), required=True)
    show_parser = subparsers.add_parser("show", help="Show a replay record summary")
    show_parser.add_argument("--source", choices=("checkpoint", "snapshot"), required=True)
    show_parser.add_argument("--tick", type=int, required=True)
    diff_parser = subparsers.add_parser("diff", help="Diff two replay records")
    diff_parser.add_argument("--left-source", choices=("checkpoint", "snapshot"), required=True)
    diff_parser.add_argument("--left-tick", type=int, required=True)
    diff_parser.add_argument("--right-source", choices=("checkpoint", "snapshot"), required=True)
    diff_parser.add_argument("--right-tick", type=int, required=True)
    return parser


def list_command_data(db_path: Path, source: ReplaySource) -> dict[str, Any]:
    ticks = list_ticks(db_path, source)
    return {
        "command": "list",
        "db": str(db_path),
        "source": source,
        "ticks": list(ticks),
        "count": len(ticks),
    }


def _list_command(payload: dict[str, Any]) -> tuple[str, ...]:
    ticks = tuple(payload["ticks"])
    summary = _format_preview(ticks)
    return (f"{payload['source']} ticks ({payload['count']}): {summary}",)


def show_command_data(db_path: Path, source: ReplaySource, tick: int) -> dict[str, Any]:
    summary = summarize_record(load_record(db_path, source, tick))
    return {
        "command": "show",
        "db": str(db_path),
        "source": summary.source,
        "tick": summary.tick,
        "granularity": summary.granularity,
        "character_ids": list(summary.character_ids),
        "event_ids": list(summary.event_ids),
        "resource_keys": list(summary.resource_keys),
        "flag_keys": list(summary.flag_keys),
    }


def _show_command(payload: dict[str, Any]) -> tuple[str, ...]:
    return (
        f"source: {payload['source']}",
        f"tick: {payload['tick']}",
        f"granularity: {payload['granularity']}",
        f"characters ({len(payload['character_ids'])}): {_format_preview(payload['character_ids'])}",
        f"events ({len(payload['event_ids'])}): {_format_preview(payload['event_ids'])}",
        f"resources ({len(payload['resource_keys'])}): {_format_preview(payload['resource_keys'])}",
        f"flags ({len(payload['flag_keys'])}): {_format_preview(payload['flag_keys'])}",
    )


def diff_command_data(
    db_path: Path,
    left_source: ReplaySource,
    left_tick: int,
    right_source: ReplaySource,
    right_tick: int,
) -> dict[str, Any]:
    left_record = load_record(db_path, left_source, left_tick)
    right_record = load_record(db_path, right_source, right_tick)
    diffs = diff_records(left_record, right_record)
    return {
        "command": "diff",
        "db": str(db_path),
        "left": {"source": left_source, "tick": left_tick},
        "right": {"source": right_source, "tick": right_tick},
        "differences": list(diffs),
    }


def _diff_command(payload: dict[str, Any]) -> tuple[str, ...]:
    left = payload["left"]
    right = payload["right"]
    header = f"diff {left['source']}:{left['tick']} -> {right['source']}:{right['tick']}"
    differences = tuple(payload["differences"])
    if not differences:
        return (header, "no differences")
    return (header,) + differences


def list_ticks(db_path: Path, source: ReplaySource) -> tuple[int, ...]:
    database = _open_database(db_path)
    connection = database.connect()
    try:
        if source == "checkpoint":
            return CheckpointRepository(connection).list_ticks()
        return WorldSnapshotRepository(connection).list_ticks()
    finally:
        connection.close()


def load_record(db_path: Path, source: ReplaySource, tick: int) -> ReplayRecord:
    database = _open_database(db_path)
    connection = database.connect()
    try:
        world = _load_world(connection, source, tick)
    finally:
        connection.close()
    return ReplayRecord(source=source, tick=tick, world=world)


def summarize_record(record: ReplayRecord) -> ReplaySummary:
    world = record.world
    return ReplaySummary(
        source=record.source,
        tick=record.tick,
        granularity=world.granularity.value,
        character_ids=tuple(sorted(world.characters)),
        event_ids=tuple(sorted(world.events)),
        resource_keys=tuple(sorted(world.resources)),
        flag_keys=tuple(sorted(world.flags)),
    )


def diff_records(left: ReplayRecord, right: ReplayRecord) -> tuple[str, ...]:
    left_payload = left.world.model_dump(mode="json")
    right_payload = right.world.model_dump(mode="json")
    return tuple(_diff_values(left_payload, right_payload, path=()))


def _open_database(db_path: Path) -> SQLiteDatabase:
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    return SQLiteDatabase(db_path)


def _load_world(connection, source: ReplaySource, tick: int) -> WorldState:
    try:
        if source == "checkpoint":
            return CheckpointRepository(connection).load(tick).world_state
        return WorldSnapshotRepository(connection).get(tick)
    except LookupError as exc:
        raise LookupError(f"{source} record not found for tick {tick}") from exc


def _diff_values(left: object, right: object, path: tuple[str, ...]) -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        return _diff_mapping(left, right, path)
    if isinstance(left, list) and isinstance(right, list):
        return _diff_sequence(left, right, path)
    if left == right:
        return []
    return [f"changed {_path_label(path)}: {_dump_value(left)} -> {_dump_value(right)}"]


def _diff_mapping(
    left: dict[str, Any],
    right: dict[str, Any],
    path: tuple[str, ...],
) -> list[str]:
    diffs: list[str] = []
    keys = tuple(sorted(set(left) | set(right)))
    for key in keys:
        next_path = path + (key,)
        if key not in left:
            diffs.append(f"added {_path_label(next_path)} = {_dump_value(right[key])}")
            continue
        if key not in right:
            diffs.append(f"removed {_path_label(next_path)} = {_dump_value(left[key])}")
            continue
        diffs.extend(_diff_values(left[key], right[key], next_path))
    return diffs


def _diff_sequence(left: list[object], right: list[object], path: tuple[str, ...]) -> list[str]:
    if left == right:
        return []
    label = _path_label(path)
    if len(left) != len(right):
        return [f"changed {label} length: {len(left)} -> {len(right)}"]
    diffs: list[str] = []
    for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
        diffs.extend(_diff_values(left_item, right_item, path + (str(index),)))
    return diffs


def _path_label(path: tuple[str, ...]) -> str:
    return ".".join(path) or "<root>"


def _dump_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _emit_output(payload: dict[str, Any], lines: tuple[str, ...], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    for line in lines:
        print(line)


def _format_preview(items: Sequence[object]) -> str:
    if not items:
        return "-"
    preview = ", ".join(str(item) for item in items[:MAX_PREVIEW_ITEMS])
    if len(items) <= MAX_PREVIEW_ITEMS:
        return preview
    remaining = len(items) - MAX_PREVIEW_ITEMS
    return f"{preview}, ... (+{remaining} more)"
