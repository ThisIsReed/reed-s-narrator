"""Repository layer for SQLite-backed persistence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from narrator.models import ActionResult, Event, WorldState


def _dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def _load_json(payload: str) -> dict[str, Any]:
    return json.loads(payload)


@dataclass(frozen=True)
class FactRecord:
    fact_id: str
    tick: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class BeliefRecord:
    character_id: str
    belief_id: str
    tick: int
    payload: dict[str, Any]


class WorldSnapshotRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, world_state: WorldState) -> None:
        payload = _dump_json(world_state.model_dump(mode="json"))
        self._connection.execute(
            """
            INSERT INTO world_snapshots(tick, state_json, seed)
            VALUES (?, ?, ?)
            ON CONFLICT(tick) DO UPDATE SET
                state_json = excluded.state_json,
                seed = excluded.seed
            """,
            (world_state.tick, payload, world_state.seed),
        )
        self._connection.commit()

    def get(self, tick: int) -> WorldState:
        row = self._connection.execute(
            "SELECT state_json FROM world_snapshots WHERE tick = ?",
            (tick,),
        ).fetchone()
        if row is None:
            raise LookupError(f"world snapshot not found for tick {tick}")
        return WorldState.model_validate(_load_json(row["state_json"]))


class EventRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, event: Event) -> None:
        payload = _dump_json(event.model_dump(mode="json"))
        self._connection.execute(
            """
            INSERT INTO events(id, tick_created, resolved, state_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tick_created = excluded.tick_created,
                resolved = excluded.resolved,
                state_json = excluded.state_json
            """,
            (event.id, event.tick_created, int(event.resolved), payload),
        )
        self._connection.commit()

    def list_by_tick(self, tick: int) -> tuple[Event, ...]:
        rows = self._connection.execute(
            "SELECT state_json FROM events WHERE tick_created = ? ORDER BY id",
            (tick,),
        ).fetchall()
        return tuple(Event.model_validate(_load_json(row["state_json"])) for row in rows)


class FactRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, record: FactRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO facts(fact_id, tick, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(fact_id) DO UPDATE SET
                tick = excluded.tick,
                payload_json = excluded.payload_json
            """,
            (record.fact_id, record.tick, _dump_json(record.payload)),
        )
        self._connection.commit()

    def list_all(self) -> tuple[FactRecord, ...]:
        rows = self._connection.execute(
            "SELECT fact_id, tick, payload_json FROM facts ORDER BY fact_id"
        ).fetchall()
        return tuple(
            FactRecord(
                fact_id=row["fact_id"],
                tick=row["tick"],
                payload=_load_json(row["payload_json"]),
            )
            for row in rows
        )


class BeliefRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, record: BeliefRecord) -> None:
        self._connection.execute(
            """
            INSERT INTO beliefs(character_id, belief_id, tick, payload_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(character_id, belief_id) DO UPDATE SET
                tick = excluded.tick,
                payload_json = excluded.payload_json
            """,
            (
                record.character_id,
                record.belief_id,
                record.tick,
                _dump_json(record.payload),
            ),
        )
        self._connection.commit()

    def list_for_character(self, character_id: str) -> tuple[BeliefRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT character_id, belief_id, tick, payload_json
            FROM beliefs
            WHERE character_id = ?
            ORDER BY belief_id
            """,
            (character_id,),
        ).fetchall()
        return tuple(
            BeliefRecord(
                character_id=row["character_id"],
                belief_id=row["belief_id"],
                tick=row["tick"],
                payload=_load_json(row["payload_json"]),
            )
            for row in rows
        )


class ActionLogRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, tick: int, result: ActionResult) -> int:
        payload = _dump_json(result.model_dump(mode="json"))
        cursor = self._connection.execute(
            """
            INSERT INTO action_log(
                tick,
                character_id,
                action_type,
                verdict,
                retry_count,
                is_fallback,
                fallback_reason,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tick,
                result.action.character_id,
                result.action.action_type,
                result.verdict.value,
                result.retry_count,
                int(result.is_fallback),
                result.fallback_reason,
                payload,
            ),
        )
        self._connection.commit()
        return int(cursor.lastrowid)

    def list_by_tick(self, tick: int) -> tuple[ActionResult, ...]:
        rows = self._connection.execute(
            "SELECT payload_json FROM action_log WHERE tick = ? ORDER BY id",
            (tick,),
        ).fetchall()
        return tuple(
            ActionResult.model_validate(_load_json(row["payload_json"])) for row in rows
        )
