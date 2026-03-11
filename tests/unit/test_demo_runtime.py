from __future__ import annotations

import pytest

from narrator.demo_runtime import build_action_result
from narrator.demo_support import build_demo_world


def test_build_action_result_raises_for_unknown_character() -> None:
    world = build_demo_world()

    with pytest.raises(LookupError, match="demo action plan not found for character: clerk"):
        build_action_result(world, "clerk", None)
