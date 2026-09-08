from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from scripts.build_us_market_news_training_features import build_training_event_frame


def test_training_event_frame_has_stable_keys_and_xnys_cutoffs() -> None:
    source = pd.DataFrame(
        {
            "symbol": ["AAPL", "MSFT"],
            "session_date": [date(2022, 3, 15), date(2022, 3, 15)],
            "bar_idx": [2, 23],
        }
    )

    result = build_training_event_frame(source)

    assert result["event_key"].tolist() == [
        "AAPL|2022-03-15|02",
        "MSFT|2022-03-15|23",
    ]
    assert result["decision_timestamp"].tolist() == [
        pd.Timestamp("2022-03-15T13:45:00Z"),
        pd.Timestamp("2022-03-15T15:30:00Z"),
    ]


def test_training_event_frame_rejects_duplicate_or_non_training_rows() -> None:
    duplicate = pd.DataFrame(
        {
            "symbol": ["AAPL", "AAPL"],
            "session_date": [date(2022, 3, 15), date(2022, 3, 15)],
            "bar_idx": [2, 2],
        }
    )
    with pytest.raises(ValueError, match="NEWS_EVENT_KEY_DUPLICATE"):
        build_training_event_frame(duplicate)

    outside = duplicate.iloc[[0]].copy()
    outside["session_date"] = date(2024, 1, 2)
    with pytest.raises(ValueError, match="TRAINING_ONLY"):
        build_training_event_frame(outside)
