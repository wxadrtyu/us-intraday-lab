from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from scripts.audit_us_market_sip_five_minute import _markdown
from us_intraday_lab.data.sip_five_minute_audit import (
    _bar_sources_by_month,
    audit_sip_five_minute,
    audit_sip_five_minute_files,
)


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


def test_file_audit_counts_required_clocks_without_materializing_missing_rows(
    tmp_path,
) -> None:
    bars = _bars(tuple(range(0, 160, 5))).assign(provider="alpaca", feed="sip")
    bars_path = tmp_path / "bars.parquet"
    decisions_path = tmp_path / "decisions.parquet"
    assets_path = tmp_path / "assets.parquet"
    bars.to_parquet(bars_path, index=False)
    pd.DataFrame(
        {
            "month": [date(2025, 1, 1)],
            "symbol": ["AAA"],
            "eligible": [True],
        }
    ).to_parquet(decisions_path, index=False)
    _assets().to_parquet(assets_path, index=False)

    result = audit_sip_five_minute_files(
        bars_glob=bars_path.as_posix(),
        decisions_path=decisions_path,
        assets_path=assets_path,
        expected_sessions=(date(2025, 1, 2),),
        historical_master_validated=True,
        source_validation={
            "partitions": 1,
            "rows": len(bars) + 1,
            "request_grid_valid": True,
            "partition_pairing_valid": True,
            "content_hashes_valid": True,
            "partial_partitions": 0,
        },
    )

    assert result["required_clock_coverage_ratio"] == 1.0
    assert result["observed_required_clock_count"] == result["required_clock_count"]
    assert result["strategy_metrics_permitted"]


def test_file_audit_refuses_unproven_source_invariants(tmp_path) -> None:
    bars = _bars((10,)).assign(provider="alpaca", feed="sip")
    bars_path = tmp_path / "bars.parquet"
    decisions_path = tmp_path / "decisions.parquet"
    assets_path = tmp_path / "assets.parquet"
    bars.to_parquet(bars_path, index=False)
    pd.DataFrame(
        {"month": [date(2025, 1, 1)], "symbol": ["AAA"], "eligible": [True]}
    ).to_parquet(decisions_path, index=False)
    _assets().to_parquet(assets_path, index=False)

    with pytest.raises(RuntimeError, match="SOURCE_VALIDATION_INVARIANTS_UNPROVEN"):
        audit_sip_five_minute_files(
            bars_glob=bars_path.as_posix(),
            decisions_path=decisions_path,
            assets_path=assets_path,
            expected_sessions=(date(2025, 1, 2),),
            historical_master_validated=True,
            source_validation={"partitions": 1, "rows": len(bars)},
        )


def test_markdown_discloses_fail_closed_reasons() -> None:
    rendered = _markdown(
        {
            "strategy_metrics_permitted": False,
            "rows": 123,
            "required_clock_coverage_ratio": 0.9,
            "rejection_reasons": ["INDEPENDENT_HISTORICAL_MASTER_MISSING"],
        }
    )

    assert "Strategy metrics permitted: **NO**" in rendered
    assert "INDEPENDENT_HISTORICAL_MASTER_MISSING" in rendered


def test_bar_sources_are_partitioned_by_calendar_month(tmp_path) -> None:
    january = tmp_path / "2025-01-batch-0000-a.parquet"
    february = tmp_path / "2025-02-batch-0000-b.parquet"
    january.touch()
    february.touch()

    sources = _bar_sources_by_month(
        (tmp_path / "*.parquet").as_posix(),
        (date(2025, 1, 1), date(2025, 2, 1)),
    )

    assert sources == {
        date(2025, 1, 1): january.as_posix(),
        date(2025, 2, 1): february.as_posix(),
    }
