"""Checkpoint persistence for replay and recovery."""

from __future__ import annotations

import pickle
import sqlite3
import zlib
from dataclasses import dataclass
from typing import Any

from narrator.models import WorldState


def _compress_world(world_state: WorldState) -> bytes:
    payload = world_state.model_dump_json().encode("utf-8")
    return zlib.compress(payload)


def _decompress_world(payload: bytes) -> WorldState:
    data = zlib.decompress(payload).decode("utf-8")
    return WorldState.model_validate_json(data)


def _dump_rng_state(rng_state: object) -> bytes:
    return pickle.dumps(rng_state, protocol=pickle.HIGHEST_PROTOCOL)


def _load_rng_state(payload: bytes) -> object:
    return pickle.loads(payload)


@dataclass(frozen=True)
class CheckpointState:
    tick: int
    world_state: WorldState
    rng_state: object


class CheckpointRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, tick: int, world_state: WorldState, rng_state: object) -> None:
        self._connection.execute(
            """
            INSERT INTO checkpoints(tick, world_snapshot, rng_state)
            VALUES (?, ?, ?)
            ON CONFLICT(tick) DO UPDATE SET
                world_snapshot = excluded.world_snapshot,
                rng_state = excluded.rng_state
            """,
            (tick, _compress_world(world_state), _dump_rng_state(rng_state)),
        )
        self._connection.commit()

    def load(self, tick: int) -> CheckpointState:
        row = self._connection.execute(
            "SELECT world_snapshot, rng_state FROM checkpoints WHERE tick = ?",
            (tick,),
        ).fetchone()
        if row is None:
            raise LookupError(f"checkpoint not found for tick {tick}")
        return CheckpointState(
            tick=tick,
            world_state=_decompress_world(row["world_snapshot"]),
            rng_state=_load_rng_state(row["rng_state"]),
        )

    def latest(self) -> CheckpointState | None:
        row = self._connection.execute(
            """
            SELECT tick, world_snapshot, rng_state
            FROM checkpoints
            ORDER BY tick DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return CheckpointState(
            tick=row["tick"],
            world_state=_decompress_world(row["world_snapshot"]),
            rng_state=_load_rng_state(row["rng_state"]),
        )

    def list_ticks(self) -> tuple[int, ...]:
        rows = self._connection.execute(
            "SELECT tick FROM checkpoints ORDER BY tick"
        ).fetchall()
        return tuple(int(row["tick"]) for row in rows)


class CheckpointManager:
    def __init__(self, repository: CheckpointRepository, interval: int) -> None:
        if interval <= 0:
            raise ValueError("interval must be greater than 0")
        self._repository = repository
        self._interval = interval

    def save_if_needed(
        self,
        tick: int,
        world_state: WorldState,
        rng_state: object,
    ) -> bool:
        if tick % self._interval != 0:
            return False
        self._repository.save(tick=tick, world_state=world_state, rng_state=rng_state)
        return True

    def restore(self, tick: int) -> CheckpointState:
        return self._repository.load(tick)
