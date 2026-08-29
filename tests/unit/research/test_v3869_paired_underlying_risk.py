from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v3869_v3968_paired_underlying_risk as subject


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("anchor_only_pair_-0.0100", -0.01), ("anchor_only_pair_0.0100", 0.01)],
)
def test_pair_confirmation_parser(mode: str, expected: float) -> None:
    assert subject.pair_confirmation(mode) == expected


def test_pair_confirmation_parser_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_PAIR_CONFIRMATION_MODE"):
        subject.pair_confirmation("anchor_only")
