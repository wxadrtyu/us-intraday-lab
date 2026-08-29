from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v2967_v3066_reentry_confirmation as subject


@pytest.mark.parametrize(
    ("mode", "expected"),
    (("anchor_only_reentry_0.0000", 0.0), ("anchor_only_reentry_0.0150", 0.015)),
)
def test_recovery_threshold(mode: str, expected: float) -> None:
    assert subject.recovery_threshold(mode) == expected


def test_recovery_threshold_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_REENTRY_CONFIRMATION_MODE"):
        subject.recovery_threshold("both_sleeves")
