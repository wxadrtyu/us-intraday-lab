from __future__ import annotations

from datetime import date

import pandas as pd

from us_intraday_lab.data.sip_five_minute_audit import audit_sip_five_minute


def _assets() -> pd.DataFrame:
    return pd.DataFrame({"symbol": ["AAA"]})


def _eligible_decisions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "session_date": [date(2025, 1, 2)],
            "symbol": ["AAA"],
            "eligible": [True],
        }
    )


def _bars(minutes: tuple[int, ...]) -> pd.DataFrame:
    base = pd.Timestamp("2025-01-02 14:30:00", tz="UTC")
    return pd.DataFrame(
        {
            "symbol": ["AAA"] * len(minutes),
            "timestamp": [base + pd.Timedelta(minutes=minute) for minute in minutes],
            "open": [100.0] * len(minutes),
            "high": [101.0] * len(minutes),
            "low": [99.0] * len(minutes),
            "close": [100.5] * len(minutes),
            "volume": [1_000] * len(minutes),
        }
    )


def test_audit_rejects_missing_delayed_entry_clock() -> None:
    result = audit_sip_five_minute(
        bars=_bars((0, 5, 10)),
        monthly_decisions=_eligible_decisions(),
        assets=_assets(),
        expected_sessions=(date(2025, 1, 2),),
        historical_master_validated=True,
    )

    assert not result["strategy_metrics_permitted"]
    assert "REQUIRED_CLOCK_COVERAGE_BELOW_95_PERCENT" in result["rejection_reasons"]


def test_audit_never_accepts_self_attested_historical_master() -> None:
    result = audit_sip_five_minute(
        bars=_bars(tuple(range(0, 150, 5))),
        monthly_decisions=_eligible_decisions(),
        assets=_assets(),
        expected_sessions=(date(2025, 1, 2),),
        historical_master_validated=False,
    )

    assert "INDEPENDENT_HISTORICAL_MASTER_MISSING" in result["rejection_reasons"]
