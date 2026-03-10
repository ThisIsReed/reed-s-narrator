from __future__ import annotations

import pytest

from narrator.persistence import SQLiteDatabase

from tests.integration.replay_support import ACTIVE_EVENT_INTERVAL, TOTAL_TICKS
from tests.integration.replay_support import AuditingRetryRuntime, replay_from_checkpoint
from tests.integration.replay_support import run_long_simulation, run_replay_cli
from tests.integration.replay_support import seed_replay_database


def test_replay_cli_lists_and_diffs_records(tmp_path) -> None:
    db_path = tmp_path / "replay.db"
    seed_replay_database(db_path)

    list_result = run_replay_cli(
        tmp_path,
        "--db",
        str(db_path),
        "list",
        "--source",
        "checkpoint",
    )
    diff_result = run_replay_cli(
        tmp_path,
        "--db",
        str(db_path),
        "diff",
        "--left-source",
        "snapshot",
        "--left-tick",
        "1",
        "--right-source",
        "checkpoint",
        "--right-tick",
        "2",
    )

    assert "checkpoint ticks (1): 2" in list_result.stdout
    assert "diff snapshot:1 -> checkpoint:2" in diff_result.stdout
    assert "changed tick: 1 -> 2" in diff_result.stdout
    assert "changed resources.food: 5.0 -> 4.0" in diff_result.stdout


@pytest.mark.asyncio
async def test_controller_survives_1000_ticks_and_replays_from_checkpoint(tmp_path) -> None:
    continuous_db = SQLiteDatabase(tmp_path / "continuous.db")
    replay_db = SQLiteDatabase(tmp_path / "replayed.db")
    continuous_db.initialize()
    replay_db.initialize()
    runtime = AuditingRetryRuntime()
    final_world, checkpoint_state = await run_long_simulation(continuous_db, runtime)
    replayed_world = await replay_from_checkpoint(replay_db, checkpoint_state)

    avg_calls_per_tick = runtime.call_count / TOTAL_TICKS
    call_ratio = avg_calls_per_tick / len(final_world.characters)

    assert final_world.tick == TOTAL_TICKS
    assert replayed_world == final_world
    assert runtime.call_count == TOTAL_TICKS // ACTIVE_EVENT_INTERVAL
    assert call_ratio < 0.4
