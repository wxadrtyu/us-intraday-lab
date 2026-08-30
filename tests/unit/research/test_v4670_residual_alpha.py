from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v4670_v5669_residual_alpha as subject


def test_campaign_has_one_thousand_frozen_versions() -> None:
    assert subject.FIRST_VERSION == 4670
    assert subject.LAST_VERSION == 5669
    assert len(subject.specifications()) == 1000


def test_every_schedule_is_causal_and_intraday() -> None:
    assert all(0 <= decision < exit_bar <= 77 for decision, exit_bar in subject.SCHEDULES)
