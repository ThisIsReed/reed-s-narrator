from __future__ import annotations

from pathlib import Path

import pytest

from narrator.agents.intent import IntentValidationError, load_action_whitelist, validate_intent


def test_validate_intent_success(tmp_path: Path) -> None:
    whitelist = _write_whitelist(tmp_path)
    intent = validate_intent(
        {
            "character_id": "c-1",
            "action_type": "move",
            "parameters": {"destination": "village", "pace": "fast"},
            "flavor_text": "他快步前往村庄。",
        },
        whitelist,
    )
    assert intent.action_type == "move"


def test_validate_intent_rejects_unknown_action(tmp_path: Path) -> None:
    whitelist = _write_whitelist(tmp_path)
    with pytest.raises(IntentValidationError, match="action not allowed"):
        validate_intent(
            {
                "character_id": "c-1",
                "action_type": "teleport",
                "parameters": {},
                "flavor_text": "瞬移",
            },
            whitelist,
        )


def test_validate_intent_rejects_missing_required_param(tmp_path: Path) -> None:
    whitelist = _write_whitelist(tmp_path)
    with pytest.raises(IntentValidationError, match="missing required parameters: destination"):
        validate_intent(
            {
                "character_id": "c-1",
                "action_type": "move",
                "parameters": {"pace": "slow"},
                "flavor_text": "慢慢移动",
            },
            whitelist,
        )


def test_validate_intent_rejects_unknown_param(tmp_path: Path) -> None:
    whitelist = _write_whitelist(tmp_path)
    with pytest.raises(IntentValidationError, match="unknown parameters: cheat"):
        validate_intent(
            {
                "character_id": "c-1",
                "action_type": "rest",
                "parameters": {"duration_hours": 6, "cheat": True},
                "flavor_text": "休息",
            },
            whitelist,
        )


def _write_whitelist(tmp_path: Path):
    content = """
version: 1
actions:
  move:
    required_params: [destination]
    optional_params: [pace]
  rest:
    required_params: []
    optional_params: [duration_hours]
"""
    path = tmp_path / "whitelist.yaml"
    path.write_text(content, encoding="utf-8")
    return load_action_whitelist(path)
