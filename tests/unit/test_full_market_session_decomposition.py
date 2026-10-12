from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from us_intraday_lab.full_market_session_decomposition import (
    FAMILIES,
    LOOKBACKS,
    REFRESH_LIFE_PAIRS,
    TOP_COUNTS,
    build_session_features,
    score_session_families,
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


def _bars(symbol: str, opens: list[float], closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2021-01-04", periods=len(opens), freq="B")
    return pd.DataFrame(
        {
            "symbol": symbol,
            "session_date": dates,
            "open": opens,
            "high": np.maximum(opens, closes) * 1.01,
            "low": np.minimum(opens, closes) * 0.99,
            "close": closes,
            "volume": np.arange(len(opens), dtype=float) + 1000.0,
            "vwap": (np.asarray(opens) + np.asarray(closes)) / 2.0,
            "trade_count": np.arange(len(opens), dtype=float) + 100.0,
        }
    )


def test_build_session_features_uses_prior_close_and_same_day_open_close() -> None:
    bars = _bars("AAA", [10.0, 12.0, 11.0], [11.0, 10.0, 12.0])

    result = build_session_features(bars)

    assert np.isnan(result.loc[0, "overnight_log_return"])
    assert result.loc[1, "overnight_log_return"] == pytest.approx(np.log(12.0 / 11.0))
    assert result.loc[1, "intraday_log_return"] == pytest.approx(np.log(10.0 / 12.0))
    assert result.loc[2, "close_above_vwap"] == 1.0
    assert result.loc[2, "dollar_volume"] == pytest.approx(12.0 * 1002.0)


def test_build_session_features_preserves_triple_zero_vwap_as_missing() -> None:
    bars = _bars("AAA", [10.0, 10.0], [10.0, 10.0])
    bars.loc[1, ["volume", "trade_count", "vwap"]] = 0.0

    result = build_session_features(bars)

    assert np.isnan(result.loc[1, "vwap"])
    assert np.isnan(result.loc[1, "close_above_vwap"])


def test_build_session_features_rejects_duplicate_and_forbidden_input() -> None:
    bars = _bars("AAA", [10.0, 10.0], [10.0, 10.0])
    duplicate = pd.concat([bars, bars.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="SESSION_DAILY_KEY_DUPLICATE"):
        build_session_features(duplicate)

    bars["headline"] = "forbidden"
    with pytest.raises(ValueError, match="FORBIDDEN_INPUT_COLUMN"):
        build_session_features(bars)


def test_build_session_features_rejects_non_sentinel_zero_vwap() -> None:
    bars = _bars("AAA", [10.0, 10.0], [10.0, 10.0])
    bars.loc[1, "vwap"] = 0.0

    with pytest.raises(ValueError, match="SESSION_DAILY_VALUES_INVALID"):
        build_session_features(bars)


def test_score_session_families_is_causal_and_leaves_short_history_missing() -> None:
    aaa = _bars("AAA", [10.0 + i for i in range(21)], [10.5 + i for i in range(21)])
    bbb = _bars("BBB", [30.0 - 0.2 * i for i in range(21)], [29.5 - 0.2 * i for i in range(21)])
    features = build_session_features(pd.concat([aaa, bbb], ignore_index=True))

    scored = score_session_families(features, 20)
    early = scored.loc[scored["session_date"].eq(pd.Timestamp("2021-01-08"))]
    last = scored.loc[scored["session_date"].eq(pd.Timestamp("2021-02-01"))]

    assert early[list(FAMILIES)].isna().all(axis=None)
    assert last[list(FAMILIES)].notna().all(axis=None)
    assert last.set_index("symbol").loc["AAA", "persistent_intraday_drift"] > last.set_index("symbol").loc["BBB", "persistent_intraday_drift"]

