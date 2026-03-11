from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from narrator.demo_support import run_demo_simulation


def test_narrate_cli_outputs_tick_range_in_rules_mode(tmp_path) -> None:
    db_path = tmp_path / "demo.db"
    asyncio.run(run_demo_simulation(db_path))

    result = run_narrate_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--from-tick",
        "1",
        "--to-tick",
        "4",
        "--rules-only",
    )

    assert "第 1 回合" in result.stdout
    assert "第 4 回合" in result.stdout
    assert "关键行动：" in result.stdout
    assert "结果变化：" in result.stdout


def test_narrate_cli_outputs_single_tick_in_rules_mode(tmp_path) -> None:
    db_path = tmp_path / "demo.db"
    asyncio.run(run_demo_simulation(db_path))

    result = run_narrate_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--tick",
        "2",
        "--rules-only",
    )

    assert "第 2 回合" in result.stdout
    assert "alarm-2" in result.stdout


def test_narrate_cli_errors_for_missing_tick(tmp_path) -> None:
    db_path = tmp_path / "demo.db"
    asyncio.run(run_demo_simulation(db_path))

    result = run_narrate_cli(
        tmp_path,
        "--db",
        str(db_path),
        "--tick",
        "99",
        "--rules-only",
        check=False,
    )

    assert result.returncode != 0
    assert "ticks not found for source snapshot: 99" in result.stderr


def run_narrate_cli(tmp_path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "narrate.py"
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=tmp_path,
        check=check,
        capture_output=True,
        text=True,
    )
