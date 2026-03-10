from __future__ import annotations

from narrator.demo import main


def test_demo_cli_outputs_current_highlights(tmp_path, capsys) -> None:
    db_path = tmp_path / "demo.db"

    exit_code = main(["--db", str(db_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "物候硬约束" in output
    assert "信息隔离与线索脱敏" in output
    assert "主循环 / checkpoint / replay" in output
    assert "checkpoint 2 vs snapshot 2: no differences" in output
    assert "actor contexts seen by active characters" in output
    assert db_path.exists()
