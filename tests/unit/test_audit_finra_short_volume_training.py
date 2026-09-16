from __future__ import annotations

import pandas as pd

from scripts.audit_finra_short_volume_training import build_coverage


def test_coverage_uses_prior_session_exact_symbol_and_last_modified() -> None:
    events = pd.DataFrame(
        {
            "symbol": ["ABC", "ABpC", "ABPC", "ABC", "ABC"],
            "session_date": [
                "2022-01-03",
                "2022-01-04",
                "2022-01-04",
                "2022-01-04",
                "2022-01-05",
            ],
            "bar_idx": [2, 2, 2, 5, 2],
        }
    )
    flow = pd.DataFrame(
        {
            "trade_date": [pd.Timestamp("2022-01-03").date(), pd.Timestamp("2022-01-03").date(), pd.Timestamp("2022-01-04").date()],
            "symbol": ["ABC", "ABpC", "ABC"],
            "short_volume": [50.0, 10.0, 60.0],
            "short_exempt_volume": [2.0, 0.0, 1.0],
            "total_volume": [100.0, 20.0, 100.0],
            "market": ["Q", "Q", "Q"],
        }
    )
    manifests = pd.DataFrame(
        {
            "trade_date": ["2022-01-03", "2022-01-04"],
            "last_modified": [
                "2022-01-03T22:19:58+00:00",
                "2022-01-06T12:00:00+00:00",
            ],
        }
    )

    covered, summary = build_coverage(events, flow, manifests)

    assert covered["coverage_reason"].tolist() == [
        "MISSING_PRIOR_SESSION",
        "COVERED",
        "SYMBOL_NOT_FOUND",
        "COVERED",
        "SOURCE_NOT_YET_AVAILABLE",
    ]
    assert covered.loc[1, "symbol"] == "ABpC"
    assert covered.loc[1, "short_ratio"] == 0.5
    assert pd.isna(covered.loc[2, "short_ratio"])
    assert summary["covered_event_rows"] == 2
    assert summary["event_rows"] == 5
    assert summary["coverage_gate"] == "BLOCKED"


def test_coverage_preserves_event_order_and_rejects_duplicate_keys() -> None:
    events = pd.DataFrame(
        {
            "symbol": ["ZZZ", "AAA"],
            "session_date": ["2022-01-04", "2022-01-04"],
            "bar_idx": [5, 2],
        }
    )
    flow = pd.DataFrame(
        columns=[
            "trade_date",
            "symbol",
            "short_volume",
            "short_exempt_volume",
            "total_volume",
            "market",
        ]
    )
    manifests = pd.DataFrame(columns=["trade_date", "last_modified"])

    covered, _ = build_coverage(events, flow, manifests)

    assert covered["symbol"].tolist() == ["ZZZ", "AAA"]
    assert covered["bar_idx"].tolist() == [5, 2]
