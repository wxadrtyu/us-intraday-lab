from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from us_intraday_lab.full_market_session_decomposition import (
    FAMILIES,
    LOOKBACKS,
    REFRESH_LIFE_PAIRS,
    TOP_COUNTS,
    AtomicCheckpoint,
    RunIdentity,
    Specification,
    build_session_features,
    evaluate_cells_sequential,
    evaluate_session_scenarios,
    passes_basic_pre_null_gates,
    performance_metrics,
    score_session_families,
    specifications,
)


def test_specifications_freeze_exact_400_cell_session_grid() -> None:
    specs = specifications()

    assert FAMILIES == (
        "persistent_overnight_drift",
        "overnight_underreaction",
        "persistent_intraday_drift",
        "gap_reversal_quality",
        "session_divergence",
    )
    assert LOOKBACKS == (20, 42, 63, 126)
    assert REFRESH_LIFE_PAIRS == ((1, 1), (5, 5), (5, 10), (10, 10), (21, 21))
    assert TOP_COUNTS == (10, 20, 40, 80)
    assert len(specs) == 400
    assert len(set(specs)) == 400
    assert all("event" not in spec.family and "fundamental" not in spec.family for spec in specs)


def _bars(symbol: str, opens: list[float], closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2021-01-04", periods=len(opens), freq="B")
    return pd.DataFrame(
        {
            "symbol": symbol,
            "session_date": dates,
            "open": opens,
            "high": np.maximum(opens, closes) * 1.01,
            "low": np.minimum(opens, closes) * 0.99,
            "close": closes,
            "volume": np.arange(len(opens), dtype=float) + 1000.0,
            "vwap": (np.asarray(opens) + np.asarray(closes)) / 2.0,
            "trade_count": np.arange(len(opens), dtype=float) + 100.0,
        }
    )


def test_build_session_features_uses_prior_close_and_same_day_open_close() -> None:
    bars = _bars("AAA", [10.0, 12.0, 11.0], [11.0, 10.0, 12.0])

    result = build_session_features(bars)

    assert np.isnan(result.loc[0, "overnight_log_return"])
    assert result.loc[1, "overnight_log_return"] == pytest.approx(np.log(12.0 / 11.0))
    assert result.loc[1, "intraday_log_return"] == pytest.approx(np.log(10.0 / 12.0))
    assert result.loc[2, "close_above_vwap"] == 1.0
    assert result.loc[2, "dollar_volume"] == pytest.approx(12.0 * 1002.0)


def test_build_session_features_preserves_triple_zero_vwap_as_missing() -> None:
    bars = _bars("AAA", [10.0, 10.0], [10.0, 10.0])
    bars.loc[1, ["volume", "trade_count", "vwap"]] = 0.0

    result = build_session_features(bars)

    assert np.isnan(result.loc[1, "vwap"])
    assert np.isnan(result.loc[1, "close_above_vwap"])


def test_build_session_features_rejects_duplicate_and_forbidden_input() -> None:
    bars = _bars("AAA", [10.0, 10.0], [10.0, 10.0])
    duplicate = pd.concat([bars, bars.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="SESSION_DAILY_KEY_DUPLICATE"):
        build_session_features(duplicate)

    bars["headline"] = "forbidden"
    with pytest.raises(ValueError, match="FORBIDDEN_INPUT_COLUMN"):
        build_session_features(bars)


def test_build_session_features_rejects_non_sentinel_zero_vwap() -> None:
    bars = _bars("AAA", [10.0, 10.0], [10.0, 10.0])
    bars.loc[1, "vwap"] = 0.0

    with pytest.raises(ValueError, match="SESSION_DAILY_VALUES_INVALID"):
        build_session_features(bars)


def test_score_session_families_is_causal_and_leaves_short_history_missing() -> None:
    aaa = _bars("AAA", [10.0 + i for i in range(21)], [10.5 + i for i in range(21)])
    bbb = _bars("BBB", [30.0 - 0.2 * i for i in range(21)], [29.5 - 0.2 * i for i in range(21)])
    features = build_session_features(pd.concat([aaa, bbb], ignore_index=True))

    scored = score_session_families(features, 20)
    early = scored.loc[scored["session_date"].eq(pd.Timestamp("2021-01-08"))]
    last = scored.loc[scored["session_date"].eq(pd.Timestamp("2021-02-01"))]

    assert early[list(FAMILIES)].isna().all(axis=None)
    assert last[list(FAMILIES)].notna().all(axis=None)
    assert last.set_index("symbol").loc["AAA", "persistent_intraday_drift"] > last.set_index("symbol").loc["BBB", "persistent_intraday_drift"]


def _portfolio_panel() -> pd.DataFrame:
    aaa = _bars("AAA", [10.0, 12.0, 12.0, 12.0], [11.0, 12.5, 12.5, 12.5])
    flat = [
        _bars(symbol, [20.0, 20.0, 20.0, 20.0], [20.0, 20.0, 20.0, 20.0])
        for symbol in ("BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ")
    ]
    panel = pd.concat([aaa, *flat], ignore_index=True)
    for family in FAMILIES:
        panel[family] = np.nan
    first_date = panel["session_date"].min()
    panel.loc[
        panel["symbol"].eq("AAA") & panel["session_date"].eq(first_date),
        list(FAMILIES),
    ] = 1.0
    first_scores = panel.loc[panel["session_date"].eq(first_date), "symbol"].map(
        lambda symbol: 1.0 if symbol == "AAA" else 0.0
    )
    for family in FAMILIES:
        panel.loc[panel["session_date"].eq(first_date), family] = first_scores.to_numpy()
    return panel


def test_overnight_family_uses_close_to_next_open_and_shared_selections() -> None:
    spec = Specification("persistent_overnight_drift", 20, 1, 1, 10)

    scenarios = evaluate_session_scenarios(_portfolio_panel(), spec)

    exposure_date = pd.Timestamp("2021-01-05")
    expected = ((12.0 / 11.0 - 1.0) / 10.0) - 0.0009
    assert scenarios["standard_9bp"].daily_returns.loc[exposure_date] == pytest.approx(expected)
    assert scenarios["cost_18bp"].daily_returns.loc[exposure_date] == pytest.approx(expected - 0.0009)
    assert scenarios["delay_1session_9bp"].daily_returns.loc[exposure_date] == 0.0
    assert scenarios["delay_1session_9bp"].daily_returns.loc[
        pd.Timestamp("2021-01-06")
    ] == pytest.approx(((12.0 / 12.5 - 1.0) / 10.0) - 0.0009)
    assert len({scenario.selection_sha256 for scenario in scenarios.values()}) == 1


def test_intraday_family_uses_next_open_to_close() -> None:
    spec = Specification("persistent_intraday_drift", 20, 1, 1, 10)

    scenarios = evaluate_session_scenarios(_portfolio_panel(), spec)

    exposure_date = pd.Timestamp("2021-01-05")
    assert scenarios["standard_9bp"].daily_returns.loc[exposure_date] == pytest.approx(((12.5 / 12.0 - 1.0) / 10.0) - 0.0009)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("missing", "SELECTED_EXPOSURE_MISSING"),
        ("zero_liquidity", "SELECTED_EXPOSURE_ZERO_LIQUIDITY"),
    ],
)
def test_selected_exposure_failure_is_cell_wide(mutation: str, reason: str) -> None:
    panel = _portfolio_panel()
    selected_date = pd.Timestamp("2021-01-05")
    target = panel["symbol"].eq("AAA") & panel["session_date"].eq(selected_date)
    if mutation == "missing":
        panel = panel.loc[~target].copy()
    else:
        panel.loc[target, ["volume", "trade_count"]] = 0.0
    spec = Specification("persistent_overnight_drift", 20, 1, 1, 10)

    scenarios = evaluate_session_scenarios(panel, spec)

    assert scenarios["standard_9bp"].valid is False
    assert scenarios["standard_9bp"].invalid_reason == reason


def _run_identity(code_sha256: str = "c" * 64) -> RunIdentity:
    return RunIdentity(
        daily_source_sha256="a" * 64,
        universe_sha256="b" * 64,
        design_sha256="d" * 64,
        code_sha256=code_sha256,
        gate_sha256="e" * 64,
    )


def test_atomic_checkpoint_resumes_only_exact_session_identity(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    checkpoint = AtomicCheckpoint.open(path, _run_identity(), total_cells=400)
    checkpoint.record_cell(0, "f" * 64)

    resumed = AtomicCheckpoint.open(path, _run_identity(), total_cells=400)

    assert resumed.cells_completed == 1
    assert len(json.loads(path.read_text("utf-8"))["chain_sha256"]) == 64
    with pytest.raises(RuntimeError, match="CHECKPOINT_IDENTITY_MISMATCH"):
        AtomicCheckpoint.open(path, _run_identity("0" * 64), total_cells=400)


def test_session_performance_metrics_and_basic_gate_are_fail_closed() -> None:
    index = pd.bdate_range("2021-01-04", periods=504)
    strong = pd.Series(np.where(np.arange(504) % 2 == 0, 0.003, 0.001), index=index)
    weak = pd.Series(np.where(np.arange(504) % 2 == 0, 0.0002, 0.0), index=index)

    strong_metrics = performance_metrics(strong)
    weak_metrics = performance_metrics(weak)

    assert strong_metrics["annualized_return"] > 0.40
    assert strong_metrics["max_drawdown"] == pytest.approx(0.0)
    assert strong_metrics["z_score"] > 3.0
    assert strong_metrics["positive_folds"] == 5
    assert passes_basic_pre_null_gates(
        {
            "standard_9bp": strong_metrics,
            "cost_18bp": strong_metrics,
            "delay_1session_9bp": strong_metrics,
        }
    )
    assert not passes_basic_pre_null_gates(
        {
            "standard_9bp": strong_metrics,
            "cost_18bp": weak_metrics,
            "delay_1session_9bp": strong_metrics,
        }
    )


def test_session_cells_resume_from_atomic_checkpoint(tmp_path: Path) -> None:
    specs = (
        Specification("persistent_overnight_drift", 20, 1, 1, 10),
        Specification("persistent_intraday_drift", 20, 1, 1, 10),
    )
    checkpoint = AtomicCheckpoint.open(
        tmp_path / "checkpoint.json", _run_identity(), total_cells=len(specs)
    )

    first = evaluate_cells_sequential(
        _portfolio_panel(), specs, checkpoint, tmp_path / "cells"
    )
    resumed = AtomicCheckpoint.open(
        tmp_path / "checkpoint.json", _run_identity(), total_cells=len(specs)
    )
    second = evaluate_cells_sequential(
        _portfolio_panel(), specs, resumed, tmp_path / "cells"
    )

    assert resumed.cells_completed == 2
    assert first == second
    assert [record["cell_index"] for record in first] == [0, 1]
    assert all(record["consumed_period"] is True for record in first)
    assert all(record["independent_oos"] is False for record in first)
