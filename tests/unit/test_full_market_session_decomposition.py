from __future__ import annotations

from us_intraday_lab.full_market_session_decomposition import (
    FAMILIES,
    LOOKBACKS,
    REFRESH_LIFE_PAIRS,
    TOP_COUNTS,
    specifications,
)


def test_specifications_freeze_exact_400_cell_session_grid() -> None:
    specs = specifications()

    assert FAMILIES == (
        "persistent_overnight_drift",
        "overnight_underreaction",
        "persistent_intraday_drift",
        "gap_reversal_quality",
        "session_divergence",
    )
    assert LOOKBACKS == (20, 42, 63, 126)
    assert REFRESH_LIFE_PAIRS == ((1, 1), (5, 5), (5, 10), (10, 10), (21, 21))
    assert TOP_COUNTS == (10, 20, 40, 80)
    assert len(specs) == 400
    assert len(set(specs)) == 400
    assert all("event" not in spec.family and "fundamental" not in spec.family for spec in specs)

