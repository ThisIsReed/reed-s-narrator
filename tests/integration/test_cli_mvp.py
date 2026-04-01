from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_unified_cli_run_replay_narrate_and_inspect_json(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    env_path = seed_runtime_inputs(tmp_path)
    config_path = Path(__file__).resolve().parents[2] / "config" / "default.yaml"

    run_result = run_main_cli(
        tmp_path,
        "run",
        "--db",
        str(db_path),
        "--config",
        str(config_path),
        "--env-file",
        str(env_path),
        "--max-ticks",
        "3",
        "--checkpoint-interval",
        "2",
        "--json",
    )
    replay_result = run_main_cli(
        tmp_path,
        "replay",
        "--db",
        str(db_path),
        "--json",
        "list",
        "--source",
        "snapshot",
    )
    narrate_result = run_main_cli(
        tmp_path,
        "narrate",
        "--db",
        str(db_path),
        "--from-tick",
        "1",
        "--to-tick",
        "3",
        "--rules-only",
        "--json",
    )
    inspect_result = run_main_cli(
        tmp_path,
        "inspect",
        "--db",
        str(db_path),
        "--json",
        "audit",
        "--tick",
        "2",
    )

    run_payload = json.loads(run_result.stdout)
    replay_payload = json.loads(replay_result.stdout)
    narrate_payload = json.loads(narrate_result.stdout)
    inspect_payload = json.loads(inspect_result.stdout)

    assert run_payload["command"] == "run"
    assert run_payload["ticks_run"] == 3
    assert run_payload["checkpoint_ticks"] == [2]
    assert run_payload["snapshot_ticks"] == [1, 2, 3]

    assert replay_payload == {
        "command": "list",
        "count": 3,
        "db": str(db_path),
        "source": "snapshot",
        "ticks": [1, 2, 3],
    }

    assert narrate_payload["command"] == "narrate"
    assert narrate_payload["ticks"] == [1, 2, 3]
    assert len(narrate_payload["entries"]) == 3
    assert narrate_payload["entries"][0]["title"] == "第 1 回合"

    assert inspect_payload["command"] == "inspect.audit"
    assert inspect_payload["tick"] == 2
    assert inspect_payload["audit"]["action_character_ids"]
    assert [stage["stage"] for stage in inspect_payload["audit"]["stages"]] == [
        "clock",
        "phenology",
        "event_pool",
        "granularity",
        "interrupt_scan",
        "knowledge_update",
        "spotlight",
        "active_agent",
        "passive_execution",
        "world_rules",
        "persistence",
        "replay_audit",
    ]


def test_unified_cli_returns_explicit_error_for_invalid_max_ticks(tmp_path) -> None:
    env_path = seed_runtime_inputs(tmp_path)
    config_path = Path(__file__).resolve().parents[2] / "config" / "default.yaml"
    result = run_main_cli(
        tmp_path,
        "run",
        "--config",
        str(config_path),
        "--env-file",
        str(env_path),
        "--max-ticks",
        "0",
        check=False,
    )

    assert result.returncode == 1
    assert "Error: max_ticks must be greater than 0" in result.stderr


def test_unified_cli_returns_explicit_error_for_missing_replay_tick(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    env_path = seed_runtime_inputs(tmp_path)
    config_path = Path(__file__).resolve().parents[2] / "config" / "default.yaml"
    run_main_cli(
        tmp_path,
        "run",
        "--db",
        str(db_path),
        "--config",
        str(config_path),
        "--env-file",
        str(env_path),
        "--max-ticks",
        "2",
    )

    result = run_main_cli(
        tmp_path,
        "replay",
        "--db",
        str(db_path),
        "show",
        "--source",
        "snapshot",
        "--tick",
        "99",
        check=False,
    )

    assert result.returncode == 1
    assert "Error: snapshot record not found for tick 99" in result.stderr


def seed_runtime_inputs(tmp_path: Path) -> Path:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            (
                "LLM_DEFAULT_PROVIDER=ollama",
                "OPENAI_MODEL_NAME=gpt-test",
                "OPENAI_API_KEY=test-key",
                "OPENAI_BASE_URL=https://example.com/openai",
                "ANTHROPIC_MODEL_NAME=claude-test",
                "ANTHROPIC_API_KEY=test-key",
                "ANTHROPIC_BASE_URL=https://example.com/anthropic",
            )
        ),
        encoding="utf-8",
    )
    return env_path


def run_main_cli(
    tmp_path: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run.py"
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=tmp_path,
        check=check,
        capture_output=True,
        text=True,
    )
