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
        for line in _list_command(Path(args.db), args.source):
            print(line)
        return 0
    if args.command == "show":
        for line in _show_command(Path(args.db), args.source, args.tick):
            print(line)
        return 0
    for line in _diff_command(
        Path(args.db),
        args.left_source,
        args.left_tick,
        args.right_source,
        args.right_tick,
    ):
        print(line)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect replay checkpoints and snapshots.")
    parser.add_argument("--db", required=True, help="SQLite database path")
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


def _list_command(db_path: Path, source: ReplaySource) -> tuple[str, ...]:
    ticks = list_ticks(db_path, source)
    summary = _format_preview(ticks)
    return (f"{source} ticks ({len(ticks)}): {summary}",)


def _show_command(db_path: Path, source: ReplaySource, tick: int) -> tuple[str, ...]:
    summary = summarize_record(load_record(db_path, source, tick))
    return (
        f"source: {summary.source}",
        f"tick: {summary.tick}",
        f"granularity: {summary.granularity}",
        f"characters ({len(summary.character_ids)}): {_format_preview(summary.character_ids)}",
        f"events ({len(summary.event_ids)}): {_format_preview(summary.event_ids)}",
        f"resources ({len(summary.resource_keys)}): {_format_preview(summary.resource_keys)}",
        f"flags ({len(summary.flag_keys)}): {_format_preview(summary.flag_keys)}",
    )


def _diff_command(
    db_path: Path,
    left_source: ReplaySource,
    left_tick: int,
    right_source: ReplaySource,
    right_tick: int,
) -> tuple[str, ...]:
    left_record = load_record(db_path, left_source, left_tick)
    right_record = load_record(db_path, right_source, right_tick)
    diffs = diff_records(left_record, right_record)
    header = f"diff {left_source}:{left_tick} -> {right_source}:{right_tick}"
    if not diffs:
        return (header, "no differences")
    return (header,) + diffs


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
    if source == "checkpoint":
        return CheckpointRepository(connection).load(tick).world_state
    return WorldSnapshotRepository(connection).get(tick)


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


def _format_preview(items: Sequence[object]) -> str:
    if not items:
        return "-"
    preview = ", ".join(str(item) for item in items[:MAX_PREVIEW_ITEMS])
    if len(items) <= MAX_PREVIEW_ITEMS:
        return preview
    remaining = len(items) - MAX_PREVIEW_ITEMS
    return f"{preview}, ... (+{remaining} more)"
