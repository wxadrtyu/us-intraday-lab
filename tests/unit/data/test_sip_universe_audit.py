from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.audit_us_market_sip_universe import _historical_master_validation
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


def test_universe_historical_master_gate_rejects_failed_report(tmp_path: Path) -> None:
    path = tmp_path / "master.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "source_namespace": "polygon_reference_tickers_v1",
                "provider": "polygon",
                "start": "2018-01-01",
                "end": "2026-03-31",
                "months": 99,
                "raw_pages": 200,
                "rows": 900_000,
                "active_rows": 600_000,
                "inactive_rows": 300_000,
                "content_hashes_valid": True,
                "page_chains_valid": True,
                "snapshots_reconstructed": True,
                "partial_files": 0,
                "provider_splicing": "FORBIDDEN",
                "rejection_reasons": ["SNAPSHOT_CONTENT_HASH_MISMATCH"],
                "passed": False,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="HISTORICAL_MASTER_VALIDATION_FAILED"):
        _historical_master_validation(path)
