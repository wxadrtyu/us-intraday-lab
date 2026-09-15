from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
from duckdb import BinderException, InvalidInputException

from scripts.build_us_market_sip_five_minute_research_catalog import (
    summarize_research_catalog,
)
from us_intraday_lab.data.sip_five_minute_research import (
    open_sip_five_minute_research_view,
)


def _write_audit(path: Path, *, permitted: bool) -> Path:
    audit = path / "audit.json"
    audit.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "strategy_metrics_permitted": permitted,
                "rejection_reasons": [] if permitted else ["BLOCKED_FOR_TEST"],
                "historical_master_validated": True,
                "historical_master_source_namespace": "polygon_reference_tickers_v1",
                "historical_master_validation_report_sha256": "a" * 64,
                "rows_spliced": 0,
                "source_validation": {
                    "request_grid_valid": True,
                    "partition_pairing_valid": True,
                    "content_hashes_valid": True,
                    "partial_partitions": 0,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return audit


def _write_source(root: Path) -> None:
    bars_path = root / "data" / "staging" / "alpaca_sip_5min_v1"
    bars_path.mkdir(parents=True)
    pd.DataFrame(
        {
            "symbol": ["A", "A", "A", "B", "C"],
            "timestamp": pd.to_datetime(
                [
                    "2021-06-01 14:35:00Z",
                    "2022-06-01 14:35:00Z",
                    "2023-06-01 14:35:00Z",
                    "2022-06-01 14:35:00Z",
                    "2022-06-01 14:35:00Z",
                ],
                utc=True,
            ),
            "open": [1.0, 2.0, 3.0, 4.0, 5.0],
            "high": [1.0, 2.0, 3.0, 4.0, 5.0],
            "low": [1.0, 2.0, 3.0, 4.0, 5.0],
            "close": [1.0, 2.0, 3.0, 4.0, 5.0],
            "volume": [10.0, 20.0, 30.0, 40.0, 50.0],
            "trade_count": [1.0, 2.0, 3.0, 4.0, 5.0],
            "vwap": [1.0, 2.0, 3.0, 4.0, 5.0],
            "asof": pd.to_datetime(
                [
                    "2021-06-30",
                    "2022-06-30",
                    "2023-06-30",
                    "2022-06-30",
                    "2022-06-30",
                ]
            ).date,
            "provider": ["alpaca"] * 5,
            "feed": ["sip"] * 5,
        }
    ).to_parquet(bars_path / "part.parquet", index=False)

    universe = root / "data" / "catalog" / "monthly_universe_sip_v2" / "test-universe"
    universe.mkdir(parents=True)
    decisions = pd.DataFrame(
        {
            "symbol": ["A", "A", "A", "B", "C"],
            "month": pd.to_datetime(
                [
                    "2021-06-01",
                    "2022-06-01",
                    "2023-06-01",
                    "2022-06-01",
                    "2022-06-01",
                ]
            ),
            "eligible": [True, True, True, False, True],
            "information_cutoff": pd.to_datetime(
                [
                    "2021-05-31",
                    "2022-05-31",
                    "2023-05-31",
                    "2022-05-31",
                    "2022-06-02",
                ]
            ),
            "median_dollar_volume": [100.0, 200.0, 300.0, 400.0, 500.0],
            "decision_reason": [
                "eligible",
                "eligible",
                "eligible",
                "ineligible",
                "future_cutoff",
            ],
        }
    )
    decisions_path = universe / "decisions.parquet"
    decisions.to_parquet(decisions_path, index=False)
    universe.joinpath("manifest.json").write_text(
        json.dumps(
            {
                "dataset_id": "test-universe",
                "start_month": "2018-04-01",
                "end_month": "2026-03-01",
                "content_sha256": hashlib.sha256(decisions_path.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


def test_view_refuses_a_blocked_audit(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path, permitted=False)

    with pytest.raises(RuntimeError, match="SIP_FIVE_MINUTE_AUDIT_BLOCKED"):
        open_sip_five_minute_research_view(root=tmp_path, audit_path=audit, role="fit")


def test_fit_view_contains_only_eligible_2022_and_2023_bars(
    tmp_path: Path,
) -> None:
    _write_source(tmp_path)
    audit = _write_audit(tmp_path, permitted=True)

    connection = open_sip_five_minute_research_view(root=tmp_path, audit_path=audit, role="fit")
    try:
        rows = connection.execute(
            """
            SELECT symbol, year(session_date), available, membership_eligible
            FROM research_bars
            ORDER BY session_date, symbol
            """
        ).fetchall()
        metadata = connection.execute(
            "SELECT role, audit_sha256, rows_spliced FROM research_metadata"
        ).fetchone()
        access_mode = connection.execute("SELECT lower(current_setting('access_mode'))").fetchone()
        with pytest.raises(InvalidInputException, match="read-only mode"):
            connection.execute("CREATE TABLE forbidden_write(value INTEGER)")
    finally:
        connection.close()

    assert rows == [("A", 2022, True, True), ("A", 2023, True, True)]
    assert metadata == ("fit", hashlib.sha256(audit.read_bytes()).hexdigest(), 0)
    assert access_mode == ("read_only",)


def test_view_rejects_unknown_date_role(tmp_path: Path) -> None:
    audit = _write_audit(tmp_path, permitted=True)

    with pytest.raises(ValueError, match="SIP_FIVE_MINUTE_ROLE_INVALID"):
        open_sip_five_minute_research_view(root=tmp_path, audit_path=audit, role="blind_test")


def test_catalog_summary_reports_role_and_rows(tmp_path: Path) -> None:
    _write_source(tmp_path)
    audit = _write_audit(tmp_path, permitted=True)

    summary = summarize_research_catalog(root=tmp_path, audit_path=audit, role="fit")

    assert summary["role"] == "fit"
    assert summary["rows"] == 2
    assert summary["symbols"] == 1
    assert summary["source_read_only"] is True


def test_failed_catalog_build_leaves_no_partial_file(tmp_path: Path) -> None:
    _write_source(tmp_path)
    bad_bars = tmp_path / "data" / "staging" / "alpaca_sip_5min_v1" / "part.parquet"
    pd.DataFrame(
        {
            "symbol": ["A"],
            "timestamp": pd.to_datetime(["2022-06-01 14:35:00Z"], utc=True),
        }
    ).to_parquet(bad_bars, index=False)
    audit = _write_audit(tmp_path, permitted=True)

    with pytest.raises(BinderException):
        open_sip_five_minute_research_view(root=tmp_path, audit_path=audit, role="fit")

    catalog = tmp_path / "data" / "catalog" / "sip_five_minute_research_v1"
    assert list(catalog.glob("*.tmp")) == []
