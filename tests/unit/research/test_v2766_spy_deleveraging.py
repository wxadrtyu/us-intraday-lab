from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v2766_v2865_spy_deleveraging as subject


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        ("same_cap_0.600_spy_replace_0.000", (0.6, 0.0)),
        ("same_cap_0.925_spy_replace_1.000", (0.925, 1.0)),
    ),
)
def test_mode_parameters(mode: str, expected: tuple[float, float]) -> None:
    assert subject.mode_parameters(mode) == expected


def test_mode_parameters_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_SPY_DELEVERAGING_MODE"):
        subject.mode_parameters("both_sleeves")
