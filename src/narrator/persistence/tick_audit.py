"""Tick-level audit persistence."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def _load_json(payload: str) -> dict[str, Any]:
    return json.loads(payload)


class TickAuditRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, tick: int, payload: dict[str, Any]) -> None:
        self._connection.execute(
            """
            INSERT INTO tick_audit(tick, payload_json)
            VALUES (?, ?)
            ON CONFLICT(tick) DO UPDATE SET payload_json = excluded.payload_json
            """,
            (tick, _dump_json(payload)),
        )
        self._connection.commit()

    def load(self, tick: int) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT payload_json FROM tick_audit WHERE tick = ?",
            (tick,),
        ).fetchone()
        if row is None:
            raise LookupError(f"tick audit not found for tick {tick}")
        return _load_json(row["payload_json"])
