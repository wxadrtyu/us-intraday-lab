from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from us_intraday_lab.data.sip_universe_audit import audit_sip_universe


def test_audit_blocks_missing_month_and_survivorship_uncertainty() -> None:
    result = audit_sip_universe(
        expected_months=(date(2022, 1, 1), date(2022, 2, 1)),
        observed_months=(date(2022, 1, 1),),
        sip_daily=pd.DataFrame(),
        iex_daily=pd.DataFrame(),
        independent_historical_master=False,
        hashes_valid=True,
        partial_partitions=0,
    )

    assert result["strategy_metrics_permitted"] is False
    assert "EXPECTED_MONTH_MISSING" in result["rejection_reasons"]
    assert result["survivorship"]["independent_historical_master"] is False


def test_audit_reports_sip_to_iex_volume_ratio_without_splicing() -> None:
    sip = pd.DataFrame(
        {"symbol": ["AAPL"], "session_date": [date(2022, 1, 3)], "volume": [4000.0]}
    )
    iex = pd.DataFrame(
        {"symbol": ["AAPL"], "session_date": [date(2022, 1, 3)], "volume": [100.0]}
    )
    result = audit_sip_universe(
        expected_months=(date(2022, 1, 1),),
        observed_months=(date(2022, 1, 1),),
        sip_daily=sip,
        iex_daily=iex,
        independent_historical_master=True,
        hashes_valid=True,
        partial_partitions=0,
    )

    assert result["source_bias"]["median_sip_to_iex_volume_ratio"] == pytest.approx(40.0)
    assert result["rows_spliced"] == 0


def test_audit_never_passes_empty_daily_or_unaudited_event_grid() -> None:
    result = audit_sip_universe(
        expected_months=(date(2022, 1, 1),),
        observed_months=(date(2022, 1, 1),),
        sip_daily=pd.DataFrame(),
        iex_daily=pd.DataFrame(),
        independent_historical_master=True,
        hashes_valid=True,
        partial_partitions=0,
    )

    assert result["daily_universe_permitted"] is False
    assert result["strategy_metrics_permitted"] is False
    assert "SIP_DAILY_EMPTY" in result["rejection_reasons"]
    assert "DECISION_EVENT_GRID_NOT_AUDITED" in result["rejection_reasons"]


def test_audit_blocks_candidate_symbols_missing_from_decision_grid() -> None:
    sip = pd.DataFrame(
        {"symbol": ["A"], "session_date": [date(2022, 1, 3)], "volume": [100.0]}
    )
    result = audit_sip_universe(
        expected_months=(date(2022, 1, 1),),
        observed_months=(date(2022, 1, 1),),
        sip_daily=sip,
        iex_daily=pd.DataFrame(),
        independent_historical_master=True,
        hashes_valid=True,
        partial_partitions=0,
        expected_candidate_symbols=("A", "DEAD"),
        decision_symbols=("A",),
    )

    assert result["missing_candidate_symbols"] == ["DEAD"]
    assert "CANDIDATE_SYMBOL_DECISIONS_MISSING" in result["rejection_reasons"]
