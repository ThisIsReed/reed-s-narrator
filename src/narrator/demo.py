"""CLI showcase for the current narrator capabilities."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from narrator.demo_support import (
    build_character,
    build_isolation_assembler,
    build_phenology_world,
    run_demo_simulation,
)
from narrator.models import StateChange
from narrator.phenology import apply_phenology
from narrator.replay import diff_records, list_ticks, load_record

MAX_DIFF_LINES = 6


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.db is not None:
        lines = asyncio.run(run_demo(Path(args.db)))
    else:
        lines = _run_with_temporary_db()
    for line in lines:
        print(line)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local showcase demo.")
    parser.add_argument("--db", help="Optional SQLite path for keeping demo artifacts")
    return parser


def _run_with_temporary_db() -> tuple[str, ...]:
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "narrator-demo.db"
        return asyncio.run(run_demo(db_path))


async def run_demo(db_path: Path) -> tuple[str, ...]:
    artifacts = await run_demo_simulation(db_path)
    return (
        "Reed's Narrator Demo",
        "",
        "1. 物候硬约束",
        *_phenology_section_lines(),
        "",
        "2. 信息隔离与线索脱敏",
        *_isolation_section_lines(),
        "",
        "3. 时间线驱动的主循环演示",
        *_timeline_section_lines(artifacts),
        "",
        "4. Replay / 持久化证据",
        *_persistence_section_lines(db_path, artifacts),
    )


def _phenology_section_lines() -> tuple[str, ...]:
    world = build_phenology_world()
    lines = []
    for tick in (45, 75, 105):
        result = apply_phenology(world, tick)
        lines.append(_phenology_summary_line(result.snapshot.tick, result.snapshot, result.state_changes))
        lines.append(_phenology_audit_line(result.audit_log))
    return tuple(lines)


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


def _timeline_section_lines(artifacts) -> tuple[str, ...]:
    lines = []
    previous_world = None
    context_map = _context_trace_map(artifacts.context_traces)
    for result in artifacts.results:
        lines.extend(_tick_lines(result, previous_world, context_map))
        previous_world = result.world
    return tuple(lines)


def _persistence_section_lines(db_path: Path, artifacts) -> tuple[str, ...]:
    belief_preview = ", ".join(_belief_preview(record) for record in artifacts.belief_records) or "-"
    audit_preview = _tick_audit_preview(artifacts.tick_audits)
    return (
        f"- snapshot ticks: {_ticks_preview(list_ticks(db_path, 'snapshot'))}",
        f"- checkpoint ticks: {_ticks_preview(list_ticks(db_path, 'checkpoint'))}",
        f"- persisted event facts: {_fact_ids(artifacts.fact_records)}",
        f"- persisted beliefs: {belief_preview}",
        f"- persisted audit preview: {audit_preview}",
        f"- checkpoint 2 vs snapshot 2: {_replay_diff_line(db_path, 'checkpoint', 2, 'snapshot', 2)}",
        f"- snapshot 1 vs snapshot 4: {_replay_diff_line(db_path, 'snapshot', 1, 'snapshot', 4)}",
    )


def _tick_lines(result, previous_world, context_map: dict[int, tuple[str, ...]]) -> tuple[str, ...]:
    event_label = ",".join(result.event_ids) or "-"
    return (
        f"- tick {result.tick}: day={result.world.phenology.day_of_year}, granularity={result.world.granularity.value}, checkpoint={_yes_no(result.checkpoint_saved)}, events={event_label}",
        f"  spotlight: {_spotlight_summary(result)}",
        f"  action: {_action_summary(result)} | reason={result.granularity_reason}",
        f"  knowledge: {_knowledge_delta_line(result.world, previous_world)}",
        f"  active contexts: {_context_preview(context_map.get(result.tick, ()))}",
        f"  audit: {_tick_audit_line(result)}",
    )


def _phenology_summary_line(tick: int, snapshot, changes: tuple[StateChange, ...]) -> str:
    festivals = ",".join(snapshot.festivals) or "-"
    return (
        f"- tick {tick}: season={snapshot.season}, climate={snapshot.climate}, "
        f"festivals={festivals} | changes={_change_preview(changes[1:])}"
    )


def _phenology_audit_line(audit_log) -> str:
    matched = [entry.rule_name for entry in audit_log if entry.matched]
    return f"  audit: {', '.join(matched) if matched else 'no matched rules'}"


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


def _knowledge_delta_line(world, previous_world) -> str:
    if previous_world is None:
        fact_ids = sorted(world.facts)
        belief_refs = sorted(_belief_refs(world))
        return _knowledge_summary(fact_ids, belief_refs, world.pending_propagation)
    new_fact_ids = sorted(set(world.facts) - set(previous_world.facts))
    new_belief_refs = sorted(_belief_refs(world) - _belief_refs(previous_world))
    return _knowledge_summary(new_fact_ids, new_belief_refs, world.pending_propagation)


def _knowledge_summary(fact_ids, belief_ids, pending_tasks) -> str:
    facts = ",".join(fact_ids) or "-"
    beliefs = ",".join(belief_ids) or "-"
    pending = ",".join(task.task_id for task in pending_tasks) or "-"
    return f"facts+={facts} | beliefs+={beliefs} | pending={pending}"


def _tick_audit_line(result) -> str:
    knowledge_stage = _stage(result, "knowledge_update")
    active_stage = _stage(result, "active_agent")
    diffusion = _find_audit_value(knowledge_stage.audit_log, "diffusion_ready")
    scheduled = _find_audit_value(active_stage.audit_log, "scheduled_diffusion")
    return f"diffusion_ready={diffusion}; scheduled_diffusion={scheduled}"


def _stage(result, stage_name: str):
    for stage in result.stages:
        if stage.stage == stage_name:
            return stage
    raise LookupError(f"stage not found: {stage_name}")


def _context_trace_map(traces: tuple[str, ...]) -> dict[int, tuple[str, ...]]:
    grouped: dict[int, list[str]] = {}
    for trace in traces:
        tick = int(trace.split()[1])
        grouped.setdefault(tick, []).append(" ".join(trace.split()[2:]))
    return {tick: tuple(items) for tick, items in grouped.items()}


def _context_preview(lines: tuple[str, ...]) -> str:
    return " | ".join(lines) if lines else "-"


def _belief_refs(world) -> set[str]:
    refs = set()
    for character_id, payloads in world.beliefs.items():
        for payload in payloads:
            refs.add(f"{character_id}:{payload['belief_id']}")
    return refs


def _find_audit_value(audit_log: tuple[str, ...], prefix: str) -> str:
    for item in audit_log:
        if item.startswith(f"{prefix}="):
            return item.split("=", 1)[1]
    return "-"


def _belief_preview(record) -> str:
    payload = record.payload
    return f"{record.character_id}:{payload['belief_id']}@{record.tick}"


def _tick_audit_preview(audits: tuple[dict[str, Any], ...]) -> str:
    if not audits:
        return "-"
    preview = []
    for audit in audits[:2]:
        tick = audit["tick"]
        pending = ",".join(audit["pending_propagation"]) or "-"
        preview.append(f"tick {tick} pending={pending}")
    return " | ".join(preview)


def _fact_ids(records) -> str:
    return ",".join(record.fact_id for record in records) or "-"


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


def _yes_no(flag: bool) -> str:
    return "yes" if flag else "no"
