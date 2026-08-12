from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from us_intraday_lab.data.alpaca_iex_acquisition import (
    BLIND_CUTOFF,
    AcquisitionWindow,
    ReadOnlyAlpacaIexDownloader,
    assess_acquired_bars,
    default_windows,
    normalize_alpaca_bars,
    publish_window_snapshot,
    verify_window_snapshot,
)
from us_intraday_lab.data.calendar import expected_minute_index


def _source_bars(session: date, symbol: str = "SPY") -> pd.DataFrame:
    rows = []
    for index, timestamp in enumerate(expected_minute_index(session)):
        price = 100.0 + index / 10_000
        rows.append(
            {
                "symbol": symbol,
                "timestamp": timestamp,
                "open": price,
                "high": price + 0.02,
                "low": price - 0.02,
                "close": price + 0.01,
                "volume": 1000 + index,
                "trade_count": 10 + index,
                "vwap": price + 0.005,
            }
        )
    return pd.DataFrame(rows)


def test_default_windows_prioritize_blind_current_and_cover_all_regimes() -> None:
    windows = default_windows(date(2026, 8, 12))

    assert windows[0] == AcquisitionWindow(
        "blind-current-2026", BLIND_CUTOFF, date(2026, 8, 12), True
    )
    assert windows[-1].start == date(2018, 10, 1)
    covered_years = {
        year
        for window in windows
        for year in range(window.start.year, window.end.year + 1)
    }
    assert covered_years == set(range(2018, 2027))
    assert all(not window.blind_test_candidate for window in windows[1:])


def test_downloader_requires_current_environment_credentials_without_reading_files() -> None:
    with pytest.raises(RuntimeError, match="ALPACA_IEX_CREDENTIAL_MISSING"):
        ReadOnlyAlpacaIexDownloader.from_environment(environ={})


def test_normalization_retains_optional_fields_and_drops_non_rth_rows() -> None:
    source = _source_bars(date(2026, 7, 2))
    outside = source.iloc[[0]].copy()
    outside["timestamp"] = pd.Timestamp("2026-07-02T12:00:00Z")

    bars = normalize_alpaca_bars(
        pd.concat([outside, source], ignore_index=True),
        ingested_at=datetime(2026, 7, 3, tzinfo=UTC),
    )

    assert len(bars) == 390
    assert {"trade_count", "vwap"}.issubset(bars.columns)
    assert bars["provider"].eq("alpaca").all()
    assert bars["feed"].eq("iex").all()
    assert bars["ingested_at"].eq(pd.Timestamp("2026-07-03T00:00:00Z")).all()


def test_quality_reports_missing_minutes_without_filling() -> None:
    session = date(2026, 7, 2)
    bars = normalize_alpaca_bars(
        _source_bars(session).drop(index=10),
        ingested_at=datetime(2026, 7, 3, tzinfo=UTC),
    )

    quality = assess_acquired_bars(bars, symbols=("SPY",), start=session, end=session)

    assert not quality["complete"]
    assert quality["missing_minutes"] == 1
    assert quality["observed_minutes"] == 389
    assert len(bars) == 389


def test_publish_is_content_addressed_and_blind_evidence_has_no_strategy_metrics(
    tmp_path: Path,
) -> None:
    session = date(2026, 7, 2)
    acquired_at = datetime(2026, 7, 3, tzinfo=UTC)
    bars = normalize_alpaca_bars(_source_bars(session), ingested_at=acquired_at)
    window = AcquisitionWindow("blind-test", session, session, True)

    manifest = publish_window_snapshot(
        bars,
        root=tmp_path,
        window=window,
        symbols=("SPY",),
    )
    snapshot = tmp_path / "data" / "lake" / "acquired" / str(manifest["dataset_id"])
    evidence = json.loads((snapshot / "quality-evidence.json").read_text("utf-8"))

    assert verify_window_snapshot(snapshot) == manifest
    assert evidence["window"]["blind_test_candidate"] is True
    assert evidence["window"]["strategy_metrics_permitted"] is False
    assert "return" not in json.dumps(evidence).lower()
    assert evidence["retained_optional_bar_fields"] == ["trade_count", "vwap"]

    second = publish_window_snapshot(
        bars,
        root=tmp_path,
        window=window,
        symbols=("SPY",),
    )
    assert second == manifest


def test_duplicate_or_extreme_adjusted_price_blocks_publication() -> None:
    session = date(2026, 7, 2)
    bars = normalize_alpaca_bars(
        _source_bars(session), ingested_at=datetime(2026, 7, 3, tzinfo=UTC)
    )
    duplicated = pd.concat([bars, bars.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="structural or adjusted-price anomaly"):
        assess_acquired_bars(duplicated, symbols=("SPY",), start=session, end=session)

    extreme = bars.copy()
    extreme.loc[100, ["open", "high", "low", "close"]] = [200.0, 201.0, 199.0, 200.0]
    with pytest.raises(ValueError, match="structural or adjusted-price anomaly"):
        assess_acquired_bars(extreme, symbols=("SPY",), start=session, end=session)

    invalid_vwap = bars.copy()
    invalid_vwap.loc[100, "vwap"] = float("nan")
    with pytest.raises(ValueError, match="structural or adjusted-price anomaly"):
        assess_acquired_bars(invalid_vwap, symbols=("SPY",), start=session, end=session)


def test_quality_blocks_rows_outside_an_early_close_grid() -> None:
    session = date(2026, 11, 27)
    bars = normalize_alpaca_bars(
        _source_bars(session), ingested_at=datetime(2026, 7, 4, tzinfo=UTC)
    )
    outside = bars.iloc[[-1]].copy()
    outside["timestamp"] = pd.Timestamp("2026-11-27T19:00:00Z")
    outside["session_date"] = session

    with pytest.raises(ValueError, match="structural or adjusted-price anomaly"):
        assess_acquired_bars(
            pd.concat([bars, outside], ignore_index=True),
            symbols=("SPY",),
            start=session,
            end=session,
        )
