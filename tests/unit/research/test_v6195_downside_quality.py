from __future__ import annotations

import evaluate_full_universe_intraday_v6195_v6294_downside_quality as subject
import numpy as np


def test_downside_target_penalizes_only_losses():
    actual = subject._downside_target(np.array([-0.2, 0.0, 0.3]))
    np.testing.assert_allclose(actual, [-0.4, 0.0, 0.3])
    assert subject.DOWNSIDE_PENALTY == 2.0
    assert subject.FALLBACK_EXPOSURE <= 1.0
