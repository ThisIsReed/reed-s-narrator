"""Domain enums shared across layers."""

from enum import Enum


class StateMode(str, Enum):
    ACTIVE = "ACTIVE"
    PASSIVE = "PASSIVE"
    DORMANT = "DORMANT"


class Granularity(str, Enum):
    YEAR = "YEAR"
    MONTH = "MONTH"
    DAY = "DAY"
    INSTANT = "INSTANT"


class Verdict(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FALLBACK = "FALLBACK"
