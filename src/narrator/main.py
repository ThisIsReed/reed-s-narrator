"""Unified CLI entrypoint for the narrator MVP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from narrator.config import load_config
from narrator.narrate import main as narrate_main
from narrator.persistence import SQLiteDatabase, TickAuditRepository
from narrator.replay import main as replay_main
from narrator.replay import list_ticks
from narrator.runtime import RunArtifacts, run_simulation_sync

if TYPE_CHECKING:
    ParserSubparsers = argparse._SubParsersAction[argparse.ArgumentParser]
else:
    ParserSubparsers = argparse._SubParsersAction


def main(argv: Sequence[str] | None = None) -> int:
    try:
        parser = _build_parser()
        args = parser.parse_args(argv)
        if args.command == "run":
            return _run_command(args)
        if args.command == "replay":
            return replay_main(_replay_argv(args))
        if args.command == "narrate":
            return narrate_main(_narrate_argv(args))
        return _inspect_command(args)
    except (FileNotFoundError, LookupError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Narrator CLI MVP.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _build_run_parser(subparsers)
    _build_replay_parser(subparsers)
    _build_narrate_parser(subparsers)
    _build_inspect_parser(subparsers)
    return parser


def _build_run_parser(subparsers: ParserSubparsers) -> None:
    parser = subparsers.add_parser("run", help="Run the formal simulation runtime")
    parser.add_argument("--db", help="SQLite database path; defaults to config.persistence.db_path")
    parser.add_argument("--config", default="config/default.yaml", help="Config path")
    parser.add_argument("--env-file", default=".env", help="Env file path")
    parser.add_argument("--max-ticks", type=int, help="Override simulation.max_ticks")
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        help="Override simulation.checkpoint_interval",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")


def _build_replay_parser(subparsers: ParserSubparsers) -> None:
    parser = subparsers.add_parser("replay", help="Inspect checkpoints and snapshots")
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    replay_subparsers = parser.add_subparsers(dest="replay_command", required=True)
    list_parser = replay_subparsers.add_parser("list", help="List ticks for a source")
    list_parser.add_argument("--source", choices=("checkpoint", "snapshot"), required=True)
    show_parser = replay_subparsers.add_parser("show", help="Show replay summary")
    show_parser.add_argument("--source", choices=("checkpoint", "snapshot"), required=True)
    show_parser.add_argument("--tick", type=int, required=True)
    diff_parser = replay_subparsers.add_parser("diff", help="Diff two replay records")
    diff_parser.add_argument("--left-source", choices=("checkpoint", "snapshot"), required=True)
    diff_parser.add_argument("--left-tick", type=int, required=True)
    diff_parser.add_argument("--right-source", choices=("checkpoint", "snapshot"), required=True)
    diff_parser.add_argument("--right-tick", type=int, required=True)


def _build_narrate_parser(subparsers: ParserSubparsers) -> None:
    parser = subparsers.add_parser("narrate", help="Build narrative summaries from replay data")
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument("--source", choices=("checkpoint", "snapshot"), default="snapshot")
    parser.add_argument("--tick", type=int, help="Single tick to narrate")
    parser.add_argument("--from-tick", type=int, help="Range start tick")
    parser.add_argument("--to-tick", type=int, help="Range end tick")
    parser.add_argument("--rules-only", action="store_true", help="Use deterministic rule rendering")
    parser.add_argument("--config", default="config/default.yaml", help="Config path for LLM mode")
    parser.add_argument("--env-file", default=".env", help="Env file path for LLM mode")
    parser.add_argument("--provider", help="Optional provider override")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")


def _build_inspect_parser(subparsers: ParserSubparsers) -> None:
    parser = subparsers.add_parser("inspect", help="Read stable CLI-side inspection models")
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    inspect_subparsers = parser.add_subparsers(dest="inspect_command", required=True)
    ticks_parser = inspect_subparsers.add_parser("ticks", help="List ticks by source")
    ticks_parser.add_argument("--source", choices=("checkpoint", "snapshot"), required=True)
    audit_parser = inspect_subparsers.add_parser("audit", help="Load tick audit payload")
    audit_parser.add_argument("--tick", type=int, required=True)


def _run_command(args: argparse.Namespace) -> int:
    app_config = load_config(args.config, args.env_file)
    db_path = Path(args.db or app_config.persistence.db_path)
    max_ticks = args.max_ticks if args.max_ticks is not None else app_config.simulation.max_ticks
    checkpoint_interval = (
        args.checkpoint_interval
        if args.checkpoint_interval is not None
        else app_config.simulation.checkpoint_interval
    )
    _require_positive("max_ticks", max_ticks)
    _require_positive("checkpoint_interval", checkpoint_interval)
    artifacts = run_simulation_sync(db_path, app_config, max_ticks, checkpoint_interval)
    payload = _run_payload(args, artifacts)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    for line in _run_lines(payload):
        print(line)
    return 0


def _inspect_command(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    if args.inspect_command == "ticks":
        payload = {
            "command": "inspect.ticks",
            "db": str(db_path),
            "source": args.source,
            "ticks": list(list_ticks(db_path, args.source)),
        }
    else:
        payload = {
            "command": "inspect.audit",
            "db": str(db_path),
            "tick": args.tick,
            "audit": _load_tick_audit(db_path, args.tick),
        }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    for line in _inspect_lines(payload):
        print(line)
    return 0


def _run_payload(args: argparse.Namespace, artifacts: RunArtifacts) -> dict[str, Any]:
    final_result = artifacts.results[-1]
    return {
        "command": "run",
        "db": str(artifacts.db_path),
        "config": str(Path(args.config)),
        "env_file": str(Path(args.env_file)),
        "max_ticks": artifacts.max_ticks,
        "checkpoint_interval": artifacts.checkpoint_interval,
        "ticks_run": len(artifacts.results),
        "final_tick": final_result.tick,
        "final_granularity": final_result.world.granularity.value,
        "checkpoint_ticks": list(artifacts.checkpoint_ticks),
        "snapshot_ticks": list(artifacts.snapshot_ticks),
        "last_event_ids": list(final_result.event_ids),
        "last_active_character_ids": list(final_result.spotlight.active_ids),
    }


def _run_lines(payload: dict[str, Any]) -> tuple[str, ...]:
    return (
        f"db: {payload['db']}",
        f"ticks_run: {payload['ticks_run']}",
        f"final_tick: {payload['final_tick']}",
        f"final_granularity: {payload['final_granularity']}",
        f"checkpoint_ticks: {_format_list_preview(payload['checkpoint_ticks'])}",
        f"snapshot_ticks: {_format_list_preview(payload['snapshot_ticks'])}",
        f"last_event_ids: {_format_list_preview(payload['last_event_ids'])}",
        f"last_active_character_ids: {_format_list_preview(payload['last_active_character_ids'])}",
    )


def _inspect_lines(payload: dict[str, Any]) -> tuple[str, ...]:
    if payload["command"] == "inspect.ticks":
        return (
            f"source: {payload['source']}",
            f"ticks: {_format_list_preview(payload['ticks'])}",
        )
    audit = payload["audit"]
    stages = tuple(stage["stage"] for stage in audit["stages"])
    return (
        f"tick: {payload['tick']}",
        f"event_ids: {_format_list_preview(audit['event_ids'])}",
        f"action_character_ids: {_format_list_preview(audit['action_character_ids'])}",
        f"stages: {_format_list_preview(stages)}",
    )


def _load_tick_audit(db_path: Path, tick: int) -> dict[str, Any]:
    database = SQLiteDatabase(db_path)
    connection = database.connect()
    try:
        return TickAuditRepository(connection).load(tick)
    finally:
        connection.close()


def _format_list_preview(items: Sequence[object]) -> str:
    if not items:
        return "-"
    return ", ".join(str(item) for item in items)


def _require_positive(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")


def _replay_argv(args: argparse.Namespace) -> list[str]:
    argv = ["--db", args.db]
    if args.json:
        argv.append("--json")
    argv.append(args.replay_command)
    if args.replay_command == "list":
        argv.extend(["--source", args.source])
        return argv
    if args.replay_command == "show":
        argv.extend(["--source", args.source, "--tick", str(args.tick)])
        return argv
    argv.extend(
        [
            "--left-source",
            args.left_source,
            "--left-tick",
            str(args.left_tick),
            "--right-source",
            args.right_source,
            "--right-tick",
            str(args.right_tick),
        ]
    )
    return argv


def _narrate_argv(args: argparse.Namespace) -> list[str]:
    argv = ["--db", args.db, "--source", args.source]
    if args.tick is not None:
        argv.extend(["--tick", str(args.tick)])
    if args.from_tick is not None:
        argv.extend(["--from-tick", str(args.from_tick)])
    if args.to_tick is not None:
        argv.extend(["--to-tick", str(args.to_tick)])
    if args.rules_only:
        argv.append("--rules-only")
    argv.extend(["--config", args.config, "--env-file", args.env_file])
    if args.provider is not None:
        argv.extend(["--provider", args.provider])
    if args.json:
        argv.append("--json")
    return argv
