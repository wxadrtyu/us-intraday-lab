from datetime import UTC, datetime, timedelta

import pytest

from us_intraday_lab.research_shadow_twelvedata import TwelveDataHistory


def test_twelve_data_history_requires_dedicated_credential() -> None:
    with pytest.raises(RuntimeError, match="TWELVEDATA_MARKET_DATA_CREDENTIAL_MISSING"):
        TwelveDataHistory.from_environment(environ={})


def test_twelve_data_history_normalizes_bars_without_trading_dependency() -> None:
    calls: list[dict[str, str]] = []

    def request(parameters: dict[str, str], api_key: str, timeout: float) -> dict[str, object]:
        calls.append(parameters)
        assert api_key == "test-key"
        assert timeout == 3.0
        return {
            "status": "ok",
            "values": [
                {
                    "datetime": "2026-08-17 13:30:00",
                    "open": "100.0",
                    "high": "101.0",
                    "low": "99.0",
                    "close": "100.5",
                    "volume": "1234",
                }
            ],
        }

    history = TwelveDataHistory(
        "test-key",
        request_json=request,
        requests_per_minute=1_000_000,
        timeout_seconds=3.0,
        sleeper=lambda _: None,
    )
    start = datetime(2026, 8, 1, tzinfo=UTC)
    bars = history.fetch(symbols=("AAPL",), start=start, end=start + timedelta(days=17))

    assert len(calls) == 2
    assert list(bars.columns) == ["symbol", "timestamp", "open", "high", "low", "close", "volume"]
    assert bars.iloc[0]["symbol"] == "AAPL"
    assert float(bars.iloc[0]["close"]) == 100.5
    assert bars.iloc[0]["timestamp"].tzinfo is not None


def test_twelve_data_history_rejects_error_payload_without_leaking_key() -> None:
    history = TwelveDataHistory(
        "secret-key",
        request_json=lambda *_: {"status": "error", "code": 429, "message": "limit"},
        sleeper=lambda _: None,
    )

    with pytest.raises(RuntimeError, match="TWELVEDATA_RESPONSE_ERROR") as error:
        history.fetch(
            symbols=("SPY",),
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 2, tzinfo=UTC),
        )

    assert "secret-key" not in str(error.value)
