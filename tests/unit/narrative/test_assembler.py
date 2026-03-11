from __future__ import annotations

from narrator.narrative import NarrativeAssembler, render_rule_entry
from narrator.persistence import SQLiteDatabase

from narrator.demo_support import run_demo_simulation


def test_narrative_assembler_builds_event_focused_beat(tmp_path) -> None:
    db_path = tmp_path / "demo.db"
    _run_demo(db_path)

    assembler = NarrativeAssembler(db_path)
    beat = assembler.build_beat(1)
    entry = render_rule_entry(beat)

    assert beat.priority == "event"
    assert beat.title == "第 1 回合"
    assert "背景推进：" in entry.summary_text
    assert "关键行动：" in entry.summary_text
    assert "未完事项：" in entry.summary_text
    assert "alarm-1" in entry.summary_text


def test_narrative_assembler_builds_knowledge_line_when_no_actions(tmp_path) -> None:
    db_path = tmp_path / "demo.db"
    _run_demo(db_path)

    assembler = NarrativeAssembler(db_path)
    source_tick = assembler.assemble_tick(4)

    assert source_tick.action_results == ()
    assert "知识传播待处理任务数" in source_tick.knowledge_summary


def _run_demo(db_path) -> None:
    import asyncio

    database = SQLiteDatabase(db_path)
    database.initialize()
    asyncio.run(run_demo_simulation(db_path))
