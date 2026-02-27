from __future__ import annotations

from narrator.core.seed import SeedManager


def test_fork_is_stable_for_same_label() -> None:
    manager = SeedManager(global_seed=123)
    assert manager.fork("rule-engine") == manager.fork("rule-engine")


def test_fork_differs_for_different_labels() -> None:
    manager = SeedManager(global_seed=123)
    assert manager.fork("clock") != manager.fork("event-pool")


def test_fork_differs_for_different_global_seed() -> None:
    left = SeedManager(global_seed=123).fork("rule")
    right = SeedManager(global_seed=456).fork("rule")
    assert left != right


def test_rng_sequence_is_reproducible() -> None:
    manager = SeedManager(global_seed=2026)
    rng_a = manager.rng("dm-agent")
    rng_b = manager.rng("dm-agent")
    assert [rng_a.random() for _ in range(3)] == [rng_b.random() for _ in range(3)]
