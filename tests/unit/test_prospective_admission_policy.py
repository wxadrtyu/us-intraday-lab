from __future__ import annotations

from us_intraday_lab.prospective_admission_policy import (
    ANNUALIZED_RETURN_FLOOR,
    EFFECTIVE_FIRST_VERSION,
    passes_primary,
)


def _observation(annualized_return: float) -> dict:
    return {
        "development_oos_2024_2025": {
            "annualized_return": annualized_return,
            "max_drawdown": 0.19,
            "information_ratio": 1.0,
        },
        "train_2022_2023": {"annualized_return": 0.01},
        "2024": {"annualized_return": 0.01},
        "2025": {"annualized_return": 0.01},
    }


def test_policy_is_prospective_and_strictly_above_40_percent():
    assert EFFECTIVE_FIRST_VERSION == 7795
    assert ANNUALIZED_RETURN_FLOOR == 0.40
    assert not passes_primary(_observation(0.40))
    assert passes_primary(_observation(0.400001))
