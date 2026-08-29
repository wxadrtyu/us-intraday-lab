from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v2466_v2565_exit_concentration as subject


@pytest.mark.parametrize(
    ("mode", "expected"),
    (("both_sleeves_cap_0.700", 0.7), ("both_sleeves_cap_1.000", 1.0)),
)
def test_concentration_cap(mode: str, expected: float) -> None:
    assert subject.concentration_cap(mode) == expected


def test_concentration_cap_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_CONCENTRATION_MODE"):
        subject.concentration_cap("anchor_only")
