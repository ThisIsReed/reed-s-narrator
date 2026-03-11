"""Simulation core exports."""

from narrator.core.clock import GlobalClock
from narrator.core.interrupt import InterruptManager, InterruptRule, InterruptSignal
from narrator.core.rule_engine import Rule, RuleContext, RuleEngine, RuleEngineResult, RuleExecutionRecord
from narrator.core.seed import SeedManager
from narrator.core.world_rules import (
    UNRESOLVED_EVENT_PRESSURE_KEY,
    UnresolvedEventPressureRule,
    build_default_rule_engine,
)

__all__ = [
    "GlobalClock",
    "InterruptManager",
    "InterruptRule",
    "InterruptSignal",
    "Rule",
    "RuleContext",
    "RuleEngine",
    "RuleEngineResult",
    "RuleExecutionRecord",
    "SeedManager",
    "UNRESOLVED_EVENT_PRESSURE_KEY",
    "UnresolvedEventPressureRule",
    "build_default_rule_engine",
]
