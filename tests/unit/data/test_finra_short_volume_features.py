from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from us_intraday_lab.data.finra_short_volume_features import build_features


def test_build_features_preserves_events_and_rolling_null_contract() -> None:
    start = date(2022, 1, 3)
    source_dates = [start + timedelta(days=index) for index in range(12)]
    rows: list[dict[str, object]] = []
    prices: list[dict[str, object]] = []
    for index, source_date in enumerate(source_dates):
        for symbol, offset in (("AAA", 0.0), ("BBB", 0.2)):
            ratio = 0.30 + index * 0.01 + offset
            rows.append(
                {
                    "symbol": symbol,
                    "session_date": source_date + timedelta(days=1),
                    "bar_idx": 2,
                    "source_date": source_date,
                    "coverage_reason": "COVERED",
                    "short_volume": ratio * 100,
                    "short_exempt_volume": 1.0,
                    "total_volume": 100.0,
                    "short_ratio": ratio,
                    "short_exempt_ratio": 0.01,
                }
            )
            prices.append(
                {
                    "trade_date": source_date,
                    "symbol": symbol,
                    "close": 100 + index * (1 if symbol == "AAA" else -1),
                }
            )
    rows.append(
        {
            "symbol": "MISSING",
            "session_date": date(2022, 1, 20),
            "bar_idx": 5,
            "source_date": date(2022, 1, 19),
            "coverage_reason": "SYMBOL_NOT_FOUND",
            "short_volume": None,
            "short_exempt_volume": None,
            "total_volume": None,
            "short_ratio": None,
            "short_exempt_ratio": None,
        }
    )

    result = build_features(pd.DataFrame(rows), pd.DataFrame(prices))

    assert len(result) == len(rows)
    assert result["symbol"].tolist() == [row["symbol"] for row in rows]
    aaa = result[result["symbol"].eq("AAA")].reset_index(drop=True)
    assert aaa.loc[:8, "short_ratio_z20"].isna().all()
    assert aaa.loc[9:, "short_ratio_z20"].notna().all()
    assert aaa.loc[4, "short_ratio_mean_5"] == pytest.approx(0.32)
    assert aaa.loc[1, "short_ratio_change_1"] == pytest.approx(0.01)
    assert result.iloc[-1]["valid_short_ratio_observations_20"] == 0
    assert pd.isna(result.iloc[-1]["short_ratio_cross_section_pct"])


def test_build_features_rejects_duplicate_event_keys() -> None:
    coverage = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "session_date": [date(2022, 1, 4), date(2022, 1, 4)],
            "bar_idx": [2, 2],
            "source_date": [date(2022, 1, 3), date(2022, 1, 3)],
            "coverage_reason": ["COVERED", "COVERED"],
            "short_volume": [1.0, 1.0],
            "short_exempt_volume": [0.0, 0.0],
            "total_volume": [2.0, 2.0],
            "short_ratio": [0.5, 0.5],
            "short_exempt_ratio": [0.0, 0.0],
        }
    )

    try:
        build_features(coverage, pd.DataFrame(columns=["trade_date", "symbol", "close"]))
    except ValueError as error:
        assert str(error) == "FINRA_FEATURE_EVENT_KEY_DUPLICATE"
    else:
        raise AssertionError("duplicate event key was accepted")
