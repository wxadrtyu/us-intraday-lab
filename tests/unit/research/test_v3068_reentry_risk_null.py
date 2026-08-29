from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import numpy as np
import validate_full_universe_intraday_v3068_reentry_risk_null as subject


def test_max_drawdown() -> None:
    assert subject.max_drawdown(np.array([0.1, -0.2])) == pytest.approx(0.2)


def test_risk_statistic_hits_one_at_both_thresholds() -> None:
    baseline = (np.array([-0.10, 0.0]),) * 3
    candidate = (np.array([-0.08, 0.0]),) * 3
    assert subject.risk_statistic(candidate, baseline) >= 1.0
