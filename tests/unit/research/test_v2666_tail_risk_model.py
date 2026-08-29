from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v2666_v2765_tail_risk_model as subject


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        ("tail_cap_0.250_q_0.700", (0.25, 0.7)),
        ("tail_cap_0.850_q_0.900", (0.85, 0.9)),
    ),
)
def test_mode_parameters(mode: str, expected: tuple[float, float]) -> None:
    assert subject.mode_parameters(mode) == expected


def test_mode_parameters_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_TAIL_RISK_MODE"):
        subject.mode_parameters("both_sleeves")
