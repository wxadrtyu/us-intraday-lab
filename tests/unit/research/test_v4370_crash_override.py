from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v4370_v4469_crash_override as subject


def test_campaign_has_one_hundred_frozen_versions() -> None:
    assert subject.FIRST_VERSION == 4370
    assert subject.LAST_VERSION == 4469
    assert len(subject.specifications()) == 100


def test_override_is_restricted_to_core_transfer_sessions() -> None:
    import numpy as np

    core_modern = np.array([True, False, False, True])
    override_state = np.array([True, True, False, False])
    assert subject._override_mask(core_modern, override_state).tolist() == [False, True, False, False]
