from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from us_intraday_lab.contracts.datasets import DatasetQuality
from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.data.canonicalize import canonicalize_tiingo_rows
from us_intraday_lab.data.quality import assess_minute_bars

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "bars"
INGESTED_AT = "2026-07-26T00:00:00Z"


@pytest.fixture
def canonical_fixture() -> Iterator[pd.DataFrame]:
    source = pd.read_csv(FIXTURE_ROOT / "minute_bars_invalid.csv")
    yield canonicalize_tiingo_rows(source, ingested_at=INGESTED_AT)


def test_synthetic_fixtures_are_small_and_have_two_symbols() -> None:
    valid = pd.read_csv(FIXTURE_ROOT / "minute_bars_valid.csv")
    invalid = pd.read_csv(FIXTURE_ROOT / "minute_bars_invalid.csv")

    assert len(valid) == 20
    assert valid["ticker"].nunique() == 2
    assert len(invalid) < 30
    assert invalid["ticker"].nunique() == 2


def test_quality_gate_fails_on_structural_errors(canonical_fixture: pd.DataFrame) -> None:
    result = assess_minute_bars(canonical_fixture)

    assert result.passed is False
    assert result.duplicate_rows == 1
    assert result.invalid_ohlc_rows == 1
    assert result.outside_session_rows == 1
    assert result.missing_expected_bars >= 1


def test_quality_gate_counts_negative_volume(canonical_fixture: pd.DataFrame) -> None:
    bars = canonical_fixture.drop_duplicates(["symbol", "timestamp"]).copy()
    bars.loc[bars.index[0], "volume"] = -1

    result = assess_minute_bars(bars)

    assert result.passed is False
    assert result.invalid_volume_rows == 1


def test_quality_gate_counts_non_monotonic_symbol_session_group() -> None:
    source = pd.read_csv(FIXTURE_ROOT / "minute_bars_valid.csv")
    bars = canonicalize_tiingo_rows(source, ingested_at=INGESTED_AT)
    out_of_order = pd.concat([bars.iloc[[1, 0]], bars.iloc[2:]], ignore_index=True)

    result = assess_minute_bars(out_of_order)

    assert result.passed is False
    assert result.non_monotonic_groups == 1


def test_missing_robustness_bars_are_counted_without_forward_fill() -> None:
    source = pd.read_csv(FIXTURE_ROOT / "minute_bars_valid.csv")
    bars = canonicalize_tiingo_rows(source, ingested_at=INGESTED_AT)
    original = bars.copy(deep=True)

    result = assess_minute_bars(bars)

    assert result.passed is True
    assert result.missing_expected_bars == 760
    pd.testing.assert_frame_equal(bars, original)


def test_missing_production_bars_fail_bootstrap_quality() -> None:
    source = pd.DataFrame(
        [
            {
                "ticker": "SPY",
                "date": "2026-07-02T13:30:00Z",
                "open": 1.0,
                "high": 1.2,
                "low": 0.9,
                "close": 1.1,
                "volume": 100,
            }
        ]
    )
    bars = canonicalize_tiingo_rows(source, ingested_at=INGESTED_AT)

    result = assess_minute_bars(bars)

    assert result.passed is False
    assert result.missing_expected_bars == 389


@pytest.mark.parametrize("missing_symbol", ["SPY", "QQQ", "IWM"])
def test_declared_wholly_absent_production_group_fails(missing_symbol: str) -> None:
    source = pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "date": "2026-07-02T13:30:00Z",
                "open": 1.0,
                "high": 1.2,
                "low": 0.9,
                "close": 1.1,
                "volume": 100,
            }
        ]
    )
    bars = canonicalize_tiingo_rows(source, ingested_at=INGESTED_AT)

    result = assess_minute_bars(
        bars,
        expected_groups={(missing_symbol, date(2026, 7, 2))},
    )

    missing_group = next(group for group in result.groups if group.symbol == missing_symbol)
    assert isinstance(result.aggregate, DatasetQuality)
    assert missing_group.observed_bars == 0
    assert missing_group.missing_expected_bars == 390
    assert missing_group.production is True
    assert result.passed is False


def test_group_results_identify_exact_robustness_quarantine_without_filling() -> None:
    session_date = date(2026, 7, 2)
    source = pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "date": timestamp.isoformat(),
                "open": 1.0,
                "high": 1.2,
                "low": 0.9,
                "close": 1.1,
                "volume": 100,
            }
            for timestamp in expected_minute_index(session_date)
        ]
    )
    bars = canonicalize_tiingo_rows(source, ingested_at=INGESTED_AT)
    original = bars.copy(deep=True)

    result = assess_minute_bars(
        bars,
        expected_groups={("MSFT", session_date), ("AAPL", session_date)},
    )

    assert [
        (group.symbol, group.session_date) for group in result.groups if group.requires_quarantine
    ] == [("MSFT", session_date)]
    assert result.groups == tuple(sorted(result.groups))
    assert result.passed is True
    pd.testing.assert_frame_equal(bars, original)


@pytest.mark.parametrize("missing_column", ["provider", "feed", "ingested_at"])
def test_quality_requires_canonical_provenance_columns(missing_column: str) -> None:
    source = pd.read_csv(FIXTURE_ROOT / "minute_bars_valid.csv")
    bars = canonicalize_tiingo_rows(source, ingested_at=INGESTED_AT).drop(columns=missing_column)

    with pytest.raises(ValueError, match="missing canonical columns"):
        assess_minute_bars(bars)


def test_quality_rejects_mixed_provider_feed_rows() -> None:
    source = pd.read_csv(FIXTURE_ROOT / "minute_bars_valid.csv")
    bars = canonicalize_tiingo_rows(source, ingested_at=INGESTED_AT)
    bars.loc[bars.index[-1], "feed"] = "sip"

    with pytest.raises(ValueError, match="exactly one provider/feed pair"):
        assess_minute_bars(bars)
