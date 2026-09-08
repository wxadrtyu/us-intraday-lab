from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from us_intraday_lab.data.news_event_features import (
    FROZEN_NEWS_LEXICON,
    build_news_features,
)


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_key": ["a", "b"],
            "symbol": ["AAPL", "MSFT"],
            "decision_timestamp": pd.to_datetime(
                ["2022-03-15T10:00:00Z", "2022-03-15T10:00:00Z"]
            ),
        }
    )


def _articles() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "news_id": ["early", "equal"],
            "available_at": pd.to_datetime(
                ["2022-03-15T09:59:59Z", "2022-03-15T10:00:00Z"]
            ),
            "source": ["wire", "wire"],
            "symbols": [("AAPL", "MSFT"), ("AAPL",)],
            "headline": ["Raises guidance", "Record profit"],
            "summary": ["Outlook improves", ""],
        }
    )


def test_features_use_strict_updated_at_cutoff_and_preserve_zero_rows() -> None:
    result = build_news_features(_events(), _articles(), FROZEN_NEWS_LEXICON)

    assert result["event_key"].tolist() == ["a", "b"]
    assert result.loc[0, "article_count_30m"] == 1
    assert result.loc[1, "article_count_30m"] == 1
    assert bool(result.loc[0, "news_available_30m"])
    assert result.loc[0, "positive_count_30m"] == 2
    assert result.loc[0, "multi_symbol_share_30m"] == pytest.approx(1.0)
    assert "headline" not in result.columns
    assert "summary" not in result.columns


def test_features_preserve_explicit_zero_news_row() -> None:
    events = _events().iloc[[1]].copy()
    articles = _articles().iloc[0:0].copy()

    result = build_news_features(events, articles, FROZEN_NEWS_LEXICON)

    assert result["event_key"].tolist() == ["b"]
    assert result.loc[0, "article_count_5d"] == 0
    assert not bool(result.loc[0, "news_available_5d"])
    assert pd.isna(result.loc[0, "latest_news_age_seconds_5d"])


def test_features_are_deterministic_and_reject_duplicate_events() -> None:
    expected = build_news_features(_events(), _articles(), FROZEN_NEWS_LEXICON)
    shuffled = build_news_features(
        _events(), _articles().iloc[::-1].reset_index(drop=True), FROZEN_NEWS_LEXICON
    )
    pd.testing.assert_frame_equal(expected, shuffled)

    duplicated = pd.concat([_events(), _events().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="NEWS_EVENT_KEY_DUPLICATE"):
        build_news_features(duplicated, _articles(), FROZEN_NEWS_LEXICON)


def test_training_mode_rejects_non_training_events() -> None:
    events = _events()
    events["decision_timestamp"] = pd.Timestamp("2024-01-02T15:00:00Z")

    with pytest.raises(ValueError, match="TRAINING_ONLY"):
        build_news_features(events, _articles(), FROZEN_NEWS_LEXICON)


def test_features_accept_parquet_list_columns_as_numpy_arrays() -> None:
    articles = _articles().iloc[[0]].copy()
    articles["symbols"] = pd.Series(
        [np.asarray(["AAPL", "MSFT"], dtype=object)], dtype=object
    )

    result = build_news_features(_events(), articles, FROZEN_NEWS_LEXICON)

    assert result["article_count_30m"].tolist() == [1, 1]
