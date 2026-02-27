"""Stable seed utilities for deterministic replay."""

from __future__ import annotations

import hashlib
import random

DEFAULT_SEED_BYTES = 8


class SeedManager:
    """Provide deterministic seed forking per subsystem label."""

    def __init__(self, global_seed: int) -> None:
        self._global_seed = global_seed

    def global_seed(self) -> int:
        return self._global_seed

    def fork(self, label: str) -> int:
        if not label:
            raise ValueError("label must not be empty")
        digest = hashlib.sha256(f"{self._global_seed}:{label}".encode("utf-8")).digest()
        return int.from_bytes(digest[:DEFAULT_SEED_BYTES], byteorder="big", signed=False)

    def rng(self, label: str) -> random.Random:
        return random.Random(self.fork(label))
