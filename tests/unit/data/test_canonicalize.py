from datetime import date
from io import StringIO

import numpy as np
import pandas as pd
import pytest

from us_intraday_lab.data.canonicalize import canonicalize_tiingo_rows


def _source_row(
    *,
    ticker: str = "spy",
    timestamp: str = "2026-07-02T13:30:00Z",
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "date": timestamp,
        "open": 1.0,
        "high": 1.2,
        "low": 0.9,
        "close": 1.1,
        "volume": 100,
    }


def test_canonicalizer_preserves_provider_and_utc_timestamp() -> None:
    source = pd.DataFrame([_source_row()])

    bars = canonicalize_tiingo_rows(source, ingested_at="2026-07-26T00:00:00Z")

    assert bars.loc[0, "symbol"] == "SPY"
    assert bars.loc[0, "provider"] == "tiingo"
    assert bars.loc[0, "feed"] == "iex"
    assert str(bars["timestamp"].dt.tz) == "UTC"


def test_canonicalizer_emits_contract_columns_and_new_york_session_date() -> None:
    source = pd.DataFrame([_source_row(timestamp="2026-07-03T00:30:00+00:00")])

    bars = canonicalize_tiingo_rows(source, ingested_at="2026-07-26T08:00:00+08:00")

    assert list(bars.columns) == [
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "provider",
        "feed",
        "session_date",
        "ingested_at",
    ]
    assert bars.loc[0, "session_date"] == date(2026, 7, 2)
    assert bars.loc[0, "ingested_at"].isoformat() == "2026-07-26T00:00:00+00:00"


def test_canonicalizer_sorts_by_symbol_and_timestamp() -> None:
    source = pd.DataFrame(
        [
            _source_row(ticker="spy", timestamp="2026-07-02T13:31:00Z"),
            _source_row(ticker="qqq", timestamp="2026-07-02T13:31:00Z"),
            _source_row(ticker="spy", timestamp="2026-07-02T13:30:00Z"),
        ]
    )

    bars = canonicalize_tiingo_rows(source, ingested_at="2026-07-26T00:00:00Z")

    assert list(zip(bars["symbol"], bars["timestamp"], strict=True)) == [
        ("QQQ", pd.Timestamp("2026-07-02T13:31:00Z")),
        ("SPY", pd.Timestamp("2026-07-02T13:30:00Z")),
        ("SPY", pd.Timestamp("2026-07-02T13:31:00Z")),
    ]


@pytest.mark.parametrize(
    "ingested_at",
    ["2026-07-26T00:00:00"],
)
def test_canonicalizer_rejects_naive_ingestion_timestamp(ingested_at: str) -> None:
    source = pd.DataFrame([_source_row()])

    with pytest.raises(ValueError, match="ingested_at must be timezone-aware"):
        canonicalize_tiingo_rows(source, ingested_at=ingested_at)


def test_canonicalizer_rejects_naive_source_timestamp() -> None:
    source = pd.DataFrame([_source_row(timestamp="2026-07-02T13:30:00")])

    with pytest.raises(ValueError, match="source timestamps must be timezone-aware"):
        canonicalize_tiingo_rows(source, ingested_at="2026-07-26T00:00:00Z")


def test_canonicalizer_rejects_duplicate_source_columns() -> None:
    source = pd.DataFrame(
        [["SPY", "2026-07-02T13:30:00Z", 1.0, 1.2, 1.1, 0.9, 1.1, 100]],
        columns=["ticker", "date", "open", "high", "high", "low", "close", "volume"],
    )

    with pytest.raises(ValueError, match="duplicate source columns"):
        canonicalize_tiingo_rows(source, ingested_at="2026-07-26T00:00:00Z")


def test_canonicalizer_normalizes_string_ohlcv_to_explicit_numeric_dtypes() -> None:
    source = pd.read_csv(
        StringIO(
            "ticker,date,open,high,low,close,volume\nSPY,2026-07-02T13:30:00Z,1.0,1.2,0.9,1.1,100\n"
        ),
        dtype="string",
    )

    bars = canonicalize_tiingo_rows(source, ingested_at="2026-07-26T00:00:00Z")

    assert {str(bars[column].dtype) for column in ("open", "high", "low", "close")} == {"float64"}
    assert str(bars["volume"].dtype) == "float64"
    assert bars.loc[0, "volume"] == 100.0


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("open", True),
        ("high", None),
        ("low", np.nan),
        ("close", np.inf),
        ("volume", -np.inf),
        ("volume", "not-a-number"),
    ],
)
def test_canonicalizer_rejects_non_numeric_null_boolean_or_nonfinite_ohlcv(
    column: str,
    value: object,
) -> None:
    source = pd.DataFrame([_source_row()])
    source[column] = source[column].astype("object")
    source.at[0, column] = value

    with pytest.raises(ValueError, match=rf"{column} must contain finite numeric values"):
        canonicalize_tiingo_rows(source, ingested_at="2026-07-26T00:00:00Z")
