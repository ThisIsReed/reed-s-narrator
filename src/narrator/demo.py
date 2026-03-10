"""CLI showcase for the current narrator capabilities."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Sequence

from narrator.models import StateChange
from narrator.phenology import apply_phenology
from narrator.replay import diff_records, list_ticks, load_record

from narrator.demo_support import (
    build_character,
    build_isolation_assembler,
    build_phenology_world,
    run_demo_simulation,
)

MAX_DIFF_LINES = 6


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.db is None:
        with TemporaryDirectory() as temp_dir:
            lines = asyncio.run(run_demo(Path(temp_dir) / "narrator-demo.db"))
    else:
        lines = asyncio.run(run_demo(Path(args.db)))
    for line in lines:
        print(line)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local showcase demo.")
    parser.add_argument("--db", help="Optional SQLite path for keeping demo artifacts")
    return parser


async def run_demo(db_path: Path) -> tuple[str, ...]:
    return (
        "Reed's Narrator Demo",
        "",
        "1. 物候硬约束",
        *_phenology_section_lines(),
        "",
        "2. 信息隔离与线索脱敏",
        *_isolation_section_lines(),
        "",
        "3. 主循环 / checkpoint / replay",
        *(await _simulation_section_lines(db_path)),
    )


def _phenology_section_lines() -> tuple[str, ...]:
    world = build_phenology_world()
    lines = []
    for tick in (45, 75, 105):
        result = apply_phenology(world, tick)
        lines.append(_phenology_summary_line(result.snapshot.tick, result.snapshot, result.state_changes))
        lines.append(_phenology_audit_line(result.audit_log))
    return tuple(lines)


def _phenology_summary_line(tick: int, snapshot, changes: tuple[StateChange, ...]) -> str:
    festivals = ",".join(snapshot.festivals) or "-"
    return (
        f"- tick {tick}: season={snapshot.season}, climate={snapshot.climate}, "
        f"festivals={festivals} | changes={_change_preview(changes[1:])}"
    )


def _phenology_audit_line(audit_log) -> str:
    matched = [entry.rule_name for entry in audit_log if entry.matched]
    return f"  audit: {', '.join(matched) if matched else 'no matched rules'}"


def _isolation_section_lines() -> tuple[str, ...]:
    assembler = build_isolation_assembler()
    hero_context = assembler.build_context(build_character("hero", "market"), tick=3)
    rival_context = assembler.build_context(build_character("rival", "palace"), tick=3)
    return (
        f"- hero facts={_entry_ids(hero_context.facts)} clues={_entry_ids(hero_context.clues)}",
        f"  hero clue text={hero_context.clues[0].content}",
        f"- rival facts={_entry_ids(rival_context.facts)} clues={_entry_ids(rival_context.clues)}",
        f"  rival audit={'; '.join(rival_context.audit_log)}",
    )


async def _simulation_section_lines(db_path: Path) -> tuple[str, ...]:
    artifacts = await run_demo_simulation(db_path)
    tick_lines = [line for result in artifacts.results for line in _tick_lines(result)]
    return (
        *tick_lines,
        "- actor contexts seen by active characters:",
        *(f"  {line}" for line in artifacts.context_traces),
        f"- snapshot ticks: {_ticks_preview(list_ticks(db_path, 'snapshot'))}",
        f"- checkpoint ticks: {_ticks_preview(list_ticks(db_path, 'checkpoint'))}",
        f"- checkpoint 2 vs snapshot 2: {_replay_diff_line(db_path, 'checkpoint', 2, 'snapshot', 2)}",
        f"- snapshot 1 vs snapshot 3: {_replay_diff_line(db_path, 'snapshot', 1, 'snapshot', 3)}",
    )


def _tick_lines(result) -> tuple[str, ...]:
    checkpoint_flag = "yes" if result.checkpoint_saved else "no"
    stage_chain = " -> ".join(stage.stage for stage in result.stages)
    return (
        (
            f"- tick {result.tick}: granularity={result.world.granularity.value}, "
            f"checkpoint={checkpoint_flag}, day={result.world.phenology.day_of_year}, "
            f"events={','.join(result.event_ids) or '-'}"
        ),
        f"  spotlight: {_spotlight_summary(result)}",
        f"  action: {_action_summary(result)} | reason={result.granularity_reason}",
        f"  stages: {stage_chain}",
        f"  pending diffusion: {len(result.world.pending_propagation)}",
    )


def _spotlight_summary(result) -> str:
    parts = []
    for entry in result.spotlight.entries:
        parts.append(f"{entry.character_id}={entry.state_mode.value}({entry.reasons[0]})")
    return ", ".join(parts)


def _action_summary(result) -> str:
    if not result.action_results:
        return "no active actions"
    action = result.action_results[0]
    return f"{action.action.character_id}:{action.action.action_type}:{action.verdict.value}"


def _replay_diff_line(
    db_path: Path,
    left_source: str,
    left_tick: int,
    right_source: str,
    right_tick: int,
) -> str:
    diffs = diff_records(
        load_record(db_path, left_source, left_tick),
        load_record(db_path, right_source, right_tick),
    )
    if not diffs:
        return "no differences"
    preview = ", ".join(diffs[:MAX_DIFF_LINES])
    if len(diffs) <= MAX_DIFF_LINES:
        return preview
    return f"{preview}, ... (+{len(diffs) - MAX_DIFF_LINES} more)"


def _change_preview(changes: tuple[StateChange, ...]) -> str:
    return ", ".join(f"{change.path}={change.after}" for change in changes) or "-"


def _entry_ids(entries) -> str:
    return ",".join(entry.entry_id for entry in entries) or "-"


def _ticks_preview(ticks: tuple[int, ...]) -> str:
    return ",".join(str(tick) for tick in ticks) or "-"
