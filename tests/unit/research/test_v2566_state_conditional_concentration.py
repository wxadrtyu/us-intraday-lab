from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v2566_v2665_state_conditional_concentration as subject


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        ("both_sleeves_conditional_cap_0.600_q_0.100", (0.6, 0.1)),
        ("both_sleeves_conditional_cap_1.000_q_0.500", (1.0, 0.5)),
    ),
)
def test_mode_parameters(mode: str, expected: tuple[float, float]) -> None:
    assert subject.mode_parameters(mode) == expected


def test_mode_parameters_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_STATE_CONCENTRATION_MODE"):
        subject.mode_parameters("both_sleeves")
