from datetime import UTC, date, datetime, timedelta, timezone

import pandas as pd
import pytest
from pydantic import ValidationError

from us_intraday_lab.long_horizon.contracts import FiveMinuteSourceDeclaration
from us_intraday_lab.long_horizon.data import canonicalize_five_minute_rows

MEMBER_SHA256 = "2aa6d1483d4aed73edad83c255f837ca95004cb9230108966ae825074289e669"


def declaration(**changes: object) -> FiveMinuteSourceDeclaration:
    payload: dict[str, object] = {
        "provider": "tiingo",
        "feed": "iex",
        "bar_size": "5min",
        "member_name": "price_intraday_vol_5min.csv",
        "member_sha256": MEMBER_SHA256,
        "symbols": ["AAPL", "QQQ"],
        "source_timezone": "America/New_York",
        "expected_start_date": "2025-01-02",
        "expected_end_date": "2026-07-02",
        "ingested_at": "2026-08-08T00:00:00Z",
    }
    payload.update(changes)
    return FiveMinuteSourceDeclaration.model_validate(payload)


def source_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "datetime": "2025-01-02 09:30:00",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 10_000,
            },
            {
                "symbol": "QQQ",
                "datetime": "2025-01-02 09:30:00",
                "open": 500.0,
                "high": 501.0,
                "low": 499.0,
                "close": 500.5,
                "volume": 20_000,
            },
        ]
    )


def test_declaration_is_closed_and_exact() -> None:
    item = declaration()

    assert item.symbols == ("AAPL", "QQQ")
    assert item.bar_size == "5min"
    assert item.ingested_at == datetime(2026, 8, 8, tzinfo=UTC)
    with pytest.raises(ValidationError):
        declaration(symbols=["QQQ", "AAPL"])
    with pytest.raises(ValidationError):
        declaration(extra_field="forbidden")


def test_declaration_requires_utc_ingestion_and_chronological_dates() -> None:
    with pytest.raises(ValidationError, match="aware UTC"):
        declaration(ingested_at=datetime(2026, 8, 8, tzinfo=timezone_plus_eight()))
    with pytest.raises(ValidationError, match="chronological"):
        declaration(expected_start_date="2026-07-03", expected_end_date="2026-07-02")


def timezone_plus_eight() -> timezone:
    return timezone(timedelta(hours=8))


def test_canonicalizer_localizes_new_york_before_utc_conversion() -> None:
    result = canonicalize_five_minute_rows(source_rows(), declaration())

    assert result.loc[0, "timestamp"] == pd.Timestamp("2025-01-02T14:30:00Z")
    assert result.loc[0, "session_date"] == date(2025, 1, 2)
    assert tuple(result.columns) == (
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
    )


def test_canonicalizer_handles_daylight_saving_offset() -> None:
    rows = source_rows()
    rows["datetime"] = "2025-07-02 09:30:00"

    result = canonicalize_five_minute_rows(rows, declaration())

    assert result.loc[0, "timestamp"] == pd.Timestamp("2025-07-02T13:30:00Z")


def test_canonicalizer_rejects_aware_source_timestamps_and_wrong_scope() -> None:
    aware = source_rows()
    aware["datetime"] = "2025-01-02T14:30:00Z"
    with pytest.raises(ValueError, match="naive America/New_York"):
        canonicalize_five_minute_rows(aware, declaration())

    wrong = source_rows()
    wrong.loc[0, "symbol"] = "SPY"
    with pytest.raises(ValueError, match="exactly AAPL and QQQ"):
        canonicalize_five_minute_rows(wrong, declaration())
