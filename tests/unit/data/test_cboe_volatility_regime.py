from __future__ import annotations

from datetime import date

import pandas as pd

from us_intraday_lab.data.cboe_volatility_regime import (
    build_event_features,
    parse_training_csv,
)


def test_parse_training_csv_discards_nontraining_rows() -> None:
    body = b"DATE,OPEN,HIGH,LOW,CLOSE\n12/31/2020,10,11,9,10\n01/04/2021,11,12,10,11\n01/03/2024,12,13,11,12\n"

    result = parse_training_csv("VIX", body)

    assert result.to_dict("records") == [
        {"source_date": date(2021, 1, 4), "vix": 11.0}
    ]


def test_parse_training_csv_accepts_single_value_schema() -> None:
    body = b"DATE,VVIX\n01/04/2021,88.5\n"

    result = parse_training_csv("VVIX", body)

    assert result.loc[0, "vvix"] == 88.5


def test_event_features_use_only_immediately_prior_equity_session() -> None:
    events = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "AAA"],
            "session_date": [date(2021, 1, 4), date(2021, 1, 5), date(2021, 1, 7)],
            "bar_idx": [2, 2, 2],
        }
    )
    indices = pd.DataFrame(
        {
            "source_date": [date(2021, 1, 4), date(2021, 1, 5)],
            "vix": [20.0, 21.0],
            "vix9d": [22.0, 23.0],
            "vvix": [100.0, 101.0],
            "ovx": [30.0, 32.0],
            "gvz": [15.0, 16.0],
            "vxeem": [25.0, 26.0],
        }
    )

    result = build_event_features(events, indices)

    assert pd.isna(result.loc[0, "source_date"])
    assert result.loc[1, "source_date"] == date(2021, 1, 4)
    assert result.loc[2, "source_date"] == date(2021, 1, 5)

