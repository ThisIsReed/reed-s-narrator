"""CLI entrypoint for narrative summaries."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Sequence

from narrator.config import load_config
from narrator.llm import LLMRouter
from narrator.narrative import NarrativeAssembler, NarrativeEntry, NarrativeReport, NarrativeWriter, render_rule_entry


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    ticks = _resolve_ticks(args)
    assembler = NarrativeAssembler(args.db, args.source)
    report = asyncio.run(_build_report(assembler, ticks, args))
    for index, entry in enumerate(report.entries):
        if index:
            print()
        print(entry.title)
        print(entry.summary_text)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate omniscient turn summaries.")
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument("--source", choices=("checkpoint", "snapshot"), default="snapshot")
    parser.add_argument("--tick", type=int, help="Single tick to narrate")
    parser.add_argument("--from-tick", type=int, help="Range start tick")
    parser.add_argument("--to-tick", type=int, help="Range end tick")
    parser.add_argument("--rules-only", action="store_true", help="Use deterministic rule rendering only")
    parser.add_argument("--config", default="config/default.yaml", help="Config path for LLM mode")
    parser.add_argument("--env-file", default=".env", help="Env file path for LLM mode")
    parser.add_argument("--provider", help="Optional provider override")
    return parser


def _resolve_ticks(args) -> tuple[int, ...]:
    if args.tick is not None:
        if args.from_tick is not None or args.to_tick is not None:
            raise ValueError("--tick cannot be combined with --from-tick/--to-tick")
        return (args.tick,)
    if args.from_tick is None or args.to_tick is None:
        raise ValueError("either --tick or both --from-tick/--to-tick must be provided")
    return tuple(range(args.from_tick, args.to_tick + 1))


async def _build_report(assembler: NarrativeAssembler, requested_ticks: tuple[int, ...], args) -> NarrativeReport:
    entries = []
    writer = None
    if not args.rules_only:
        app_config = load_config(args.config, args.env_file)
        router = LLMRouter.from_config(app_config.llm.model_dump(mode="python"))
        writer = NarrativeWriter(router, provider_name=args.provider)

    ticks = _validate_requested_ticks(assembler, requested_ticks)
    for tick in ticks:
        beat = assembler.build_beat(tick)
        entry = render_rule_entry(beat) if writer is None else await writer.write(beat)
        entries.append(entry)
    return NarrativeReport(source=assembler.source, ticks=ticks, entries=tuple(entries))


def _validate_requested_ticks(
    assembler: NarrativeAssembler,
    requested_ticks: tuple[int, ...],
) -> tuple[int, ...]:
    available = set(assembler.ticks)
    missing = [tick for tick in requested_ticks if tick not in available]
    if missing:
        joined = ",".join(str(tick) for tick in missing)
        raise LookupError(f"ticks not found for source {assembler.source}: {joined}")
    return requested_ticks
