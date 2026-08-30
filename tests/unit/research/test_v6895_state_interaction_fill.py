from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v6895_v6994_state_interaction_fill as subject


def test_campaign_has_one_hundred_frozen_versions():
    subject._configure()
    assert subject.FIRST_VERSION == 6895
    assert subject.LAST_VERSION == 6994
    assert len(subject.STATE_FAMILIES) == 10
    assert len(subject.campaign.specifications()) == 100


def test_every_state_family_is_multifactor():
    assert all(len(factors) >= 4 for factors in subject.STATE_FAMILIES.values())
