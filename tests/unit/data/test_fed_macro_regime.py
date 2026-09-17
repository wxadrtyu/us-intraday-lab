from datetime import date

import pandas as pd

from us_intraday_lab.data.fed_macro_regime import build_event_features, parse_series_csv


def test_parse_series_csv_preserves_missingness_and_training_boundary() -> None:
    body = b"observation_date,DGS2\n2020-12-31,0.1\n2021-01-04,0.2\n2021-01-05,.\n2024-01-02,4.0\n"

    result = parse_series_csv("DGS2", body)

    assert result["source_date"].tolist() == [date(2021, 1, 4), date(2021, 1, 5)]
    assert result["dgs2"].iloc[0] == 0.2
    assert pd.isna(result["dgs2"].iloc[1])


def test_features_join_only_immediately_prior_training_session() -> None:
    events = pd.DataFrame({
        "symbol": ["AAA", "AAA", "AAA"],
        "session_date": [date(2021, 1, 4), date(2021, 1, 5), date(2024, 1, 3)],
        "bar_idx": [2, 2, 2],
    })
    macro = pd.DataFrame({
        "source_date": [date(2021, 1, 4)], "dgs2": [0.2], "dgs10": [1.0],
        "dgs30": [1.5], "dfii10": [-1.0], "t10yie": [2.0], "dtwexbgs": [110.0],
    })

    result = build_event_features(events, macro)

    assert len(result) == 2
    assert pd.isna(result.loc[0, "source_date"])
    assert result.loc[1, "source_date"] == date(2021, 1, 4)
