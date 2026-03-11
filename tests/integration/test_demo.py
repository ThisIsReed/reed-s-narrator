from __future__ import annotations

from narrator.demo import main


def test_demo_cli_outputs_current_highlights(tmp_path, capsys) -> None:
    db_path = tmp_path / "demo.db"

    exit_code = main(["--db", str(db_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "演示场景概览" in output
    assert "物候硬约束" in output
    assert "信息隔离与线索脱敏" in output
    assert "时间线驱动的主循环演示" in output
    assert "Narrative Beat 回放" in output
    assert "Replay / 持久化证据" in output
    assert "最终世界状态" in output
    assert "scripted incidents: tick 1:alarm-1->scout@watchtower" in output
    assert "flavor: Scout climbs the tower to inspect the beacon." in output
    assert "第 1 回合 [event]" in output
    assert "checkpoint 2 vs snapshot 2: no differences" in output
    assert "persisted beliefs:" in output
    assert "tick 4: day=4" in output
    assert "belief coverage: captain=2, clerk=1, hermit=0, merchant=1, scout=2" in output
    assert "diffusion_ready=action:3:merchant:clerk:4" in output
    assert db_path.exists()


def test_demo_cli_runs_without_explicit_db(capsys) -> None:
    exit_code = main([])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Reed's Narrator Demo" in output
    assert "0. 演示场景概览" in output
    assert "snapshot ticks: 1,2,3,4" in output
