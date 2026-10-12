from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from us_intraday_lab.full_market_daily_multifactor import (
    FAMILIES,
    HOLDING_SESSIONS,
    REBALANCE_SESSIONS,
    TOP_COUNTS,
    AtomicCheckpoint,
    RunIdentity,
    Specification,
    attach_point_in_time_eligibility,
    build_daily_features,
    evaluate_cells_sequential,
    evaluate_scenarios,
    passes_basic_pre_null_gates,
    performance_metrics,
    score_families,
    specifications,
    validate_monthly_universe,
)


def _universe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB", "BBB"],
            "month": pd.to_datetime(
                ["2021-01-01", "2021-02-01", "2021-01-01", "2021-02-01"]
            ),
            "eligible": [True, False, False, True],
            "information_cutoff": pd.to_datetime(
                ["2020-12-31", "2021-01-29", "2020-12-31", "2021-01-29"]
            ),
        }
    )


def test_specifications_freeze_exact_full_market_400_cell_grid() -> None:
    specs = specifications()

    assert len(specs) == 400
    assert len(set(specs)) == 400
    assert len(FAMILIES) == 5
    assert REBALANCE_SESSIONS == (5, 10, 20, 21)
    assert HOLDING_SESSIONS == (5, 10, 20, 42)
    assert TOP_COUNTS == (10, 20, 40, 80, 120)


def test_validate_monthly_universe_rejects_duplicate_symbol_month() -> None:
    universe = pd.concat([_universe(), _universe().iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="UNIVERSE_KEY_DUPLICATE"):
        validate_monthly_universe(universe)


def test_validate_monthly_universe_rejects_noncausal_cutoff() -> None:
    universe = _universe()
    universe.loc[0, "information_cutoff"] = pd.Timestamp("2021-01-01")

    with pytest.raises(ValueError, match="UNIVERSE_CUTOFF_NOT_PRIOR"):
        validate_monthly_universe(universe)


def test_attach_point_in_time_eligibility_uses_same_calendar_month() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB", "BBB"],
            "session_date": pd.to_datetime(
                ["2021-01-15", "2021-02-12", "2021-01-15", "2021-02-12"]
            ),
            "open": [10.0, 11.0, 20.0, 21.0],
            "high": [10.5, 11.5, 20.5, 21.5],
            "low": [9.5, 10.5, 19.5, 20.5],
            "close": [10.2, 11.2, 20.2, 21.2],
            "volume": [1000, 1100, 2000, 2100],
            "vwap": [10.1, 11.1, 20.1, 21.1],
            "trade_count": [100, 110, 200, 210],
        }
    )

    attached = attach_point_in_time_eligibility(bars, _universe())

    assert list(attached[["symbol", "session_date"]].itertuples(index=False, name=None)) == [
        ("AAA", pd.Timestamp("2021-01-15")),
        ("BBB", pd.Timestamp("2021-02-12")),
    ]
    assert attached["universe_month"].tolist() == list(
        pd.to_datetime(["2021-01-01", "2021-02-01"])
    )


def test_attach_point_in_time_eligibility_rejects_duplicate_daily_key() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "session_date": pd.to_datetime(["2021-01-15", "2021-01-15"]),
            "open": [10.0, 10.0],
            "high": [10.5, 10.5],
            "low": [9.5, 9.5],
            "close": [10.2, 10.2],
            "volume": [1000, 1000],
            "vwap": [10.1, 10.1],
            "trade_count": [100, 100],
        }
    )

    with pytest.raises(ValueError, match="DAILY_KEY_DUPLICATE"):
        attach_point_in_time_eligibility(bars, _universe())


def test_attach_point_in_time_eligibility_rejects_forbidden_columns() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "session_date": pd.to_datetime(["2021-01-15"]),
            "open": [10.0],
            "high": [10.5],
            "low": [9.5],
            "close": [10.2],
            "volume": [1000],
            "vwap": [10.1],
            "trade_count": [100],
            "headline": ["forbidden"],
        }
    )

    with pytest.raises(ValueError, match="FORBIDDEN_INPUT_COLUMN"):
        attach_point_in_time_eligibility(bars, _universe())


def test_zero_liquidity_source_row_preserves_missing_vwap() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "session_date": pd.to_datetime(["2021-01-15"]),
            "open": [10.0],
            "high": [10.0],
            "low": [10.0],
            "close": [10.0],
            "volume": [0.0],
            "vwap": [0.0],
            "trade_count": [0.0],
        }
    )

    attached = attach_point_in_time_eligibility(bars, _universe())

    assert len(attached) == 1
    assert np.isnan(attached.iloc[0]["vwap"])


def _feature_bars(count: int = 300) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-02", periods=count)
    rows: list[dict[str, object]] = []
    for symbol, phase in (("AAA", 0.0), ("BBB", 0.7), ("CCC", 1.4)):
        for ordinal, session in enumerate(dates):
            log_close = 3.0 + 0.001 * ordinal + 0.015 * np.sin(ordinal / 9 + phase)
            close = float(np.exp(log_close))
            rows.append(
                {
                    "symbol": symbol,
                    "session_date": session,
                    "open": close * 0.999,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": float(1_000_000 + ordinal * 1000 + phase * 10_000),
                    "vwap": close * (0.998 if symbol != "CCC" else 1.002),
                    "trade_count": float(10_000 + ordinal),
                }
            )
    return pd.DataFrame(rows)


def test_build_daily_features_is_causal_and_uses_prior_breakout_high() -> None:
    bars = _feature_bars()
    baseline = build_daily_features(bars)
    cutoff = pd.Timestamp("2021-01-29")
    before = baseline.loc[baseline["session_date"].le(cutoff)].reset_index(drop=True)
    mutated = bars.copy()
    mutated.loc[mutated["session_date"].gt(cutoff), "close"] *= 20.0

    after = build_daily_features(mutated)
    after = after.loc[after["session_date"].le(cutoff)].reset_index(drop=True)

    pd.testing.assert_frame_equal(before, after)
    aaa = baseline.loc[baseline["symbol"].eq("AAA")].reset_index(drop=True)
    prior_high = bars.loc[bars["symbol"].eq("AAA"), "close"].iloc[-127:-1].max()
    assert aaa.iloc[-1]["breakout_126"] == pytest.approx(
        bars.loc[bars["symbol"].eq("AAA"), "close"].iloc[-1] / prior_high - 1.0
    )
    assert aaa.iloc[-1]["return_5"] == pytest.approx(
        np.log(
            bars.loc[bars["symbol"].eq("AAA"), "close"].iloc[-1]
            / bars.loc[bars["symbol"].eq("AAA"), "close"].iloc[-6]
        )
    )
    assert np.isfinite(aaa.iloc[-1]["residual_momentum_252_21"])


def test_score_families_enforces_preregistered_gates() -> None:
    features = build_daily_features(_feature_bars())
    last_date = features["session_date"].max()
    cross_section = features.loc[features["session_date"].eq(last_date)].copy()
    cross_section.loc[cross_section["symbol"].eq("BBB"), "return_126"] = -0.01
    cross_section.loc[cross_section["symbol"].eq("CCC"), "vwap_displacement_20"] = -0.01

    scored = score_families(cross_section)

    bbb = scored.loc[scored["symbol"].eq("BBB")].iloc[0]
    ccc = scored.loc[scored["symbol"].eq("CCC")].iloc[0]
    assert np.isnan(bbb["low_vol_trend"])
    assert np.isnan(bbb["trend_conditioned_reversal"])
    assert np.isnan(ccc["liquidity_confirmed_breakout"])
    assert scored["residual_momentum"].notna().all()


def _portfolio_panel() -> pd.DataFrame:
    dates = pd.bdate_range("2021-01-04", periods=13)
    rows: list[dict[str, object]] = []
    for ordinal, session in enumerate(dates):
        for symbol, score, base in (("AAA", 2.0, 100.0), ("BBB", 1.0, 200.0)):
            open_price = base + ordinal
            rows.append(
                {
                    "symbol": symbol,
                    "session_date": session,
                    "open": open_price,
                    "close": open_price + 1.0,
                    "volume": 1_000_000.0,
                    "trade_count": 10_000.0,
                    **{family: score for family in FAMILIES},
                }
            )
    return pd.DataFrame(rows)


def test_scenarios_share_selection_and_apply_cost_and_delay() -> None:
    spec = Specification("residual_momentum", 5, 5, 1)

    scenarios = evaluate_scenarios(_portfolio_panel(), spec)

    standard = scenarios["standard_9bp"]
    stress = scenarios["cost_18bp"]
    delayed = scenarios["delay_1session_9bp"]
    assert standard.valid and stress.valid and delayed.valid
    assert standard.selection_sha256 == stress.selection_sha256 == delayed.selection_sha256
    assert standard.cohorts == 2
    assert standard.daily_returns.iloc[1] == pytest.approx(1.0 / 101.0 - 0.0009)
    assert stress.daily_returns.iloc[1] == pytest.approx(1.0 / 101.0 - 0.0018)
    assert delayed.daily_returns.iloc[2] == pytest.approx(1.0 / 102.0 - 0.0009)


def test_scenarios_fail_closed_when_selected_path_has_missing_bar() -> None:
    panel = _portfolio_panel()
    panel = panel.loc[
        ~(
            panel["symbol"].eq("AAA")
            & panel["session_date"].eq(pd.Timestamp("2021-01-07"))
        )
    ]
    spec = Specification("residual_momentum", 5, 5, 1)

    scenarios = evaluate_scenarios(panel, spec)

    assert all(not result.valid for result in scenarios.values())
    assert all(result.invalid_reason == "SELECTED_PATH_MISSING" for result in scenarios.values())


def test_scenarios_fail_closed_when_selected_path_has_zero_liquidity() -> None:
    panel = _portfolio_panel()
    mask = panel["symbol"].eq("AAA") & panel["session_date"].eq(
        pd.Timestamp("2021-01-07")
    )
    panel.loc[mask, ["volume", "trade_count"]] = 0.0
    spec = Specification("residual_momentum", 5, 5, 1)

    scenarios = evaluate_scenarios(panel, spec)

    assert all(not result.valid for result in scenarios.values())
    assert all(
        result.invalid_reason == "SELECTED_PATH_ZERO_LIQUIDITY"
        for result in scenarios.values()
    )


def _run_identity(code_sha256: str = "c" * 64) -> RunIdentity:
    return RunIdentity(
        daily_source_sha256="a" * 64,
        universe_sha256="b" * 64,
        design_sha256="d" * 64,
        code_sha256=code_sha256,
        gate_sha256="e" * 64,
    )


def test_atomic_checkpoint_resumes_only_exact_identity(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    checkpoint = AtomicCheckpoint.open(path, _run_identity(), total_cells=400)
    checkpoint.record_cell(0, "f" * 64)

    resumed = AtomicCheckpoint.open(path, _run_identity(), total_cells=400)

    assert resumed.cells_completed == 1
    state = json.loads(path.read_text("utf-8"))
    assert state["cells_completed"] == 1
    assert len(state["chain_sha256"]) == 64
    with pytest.raises(RuntimeError, match="CHECKPOINT_IDENTITY_MISMATCH"):
        AtomicCheckpoint.open(path, _run_identity("0" * 64), total_cells=400)


def test_atomic_checkpoint_rejects_out_of_order_progress(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    checkpoint = AtomicCheckpoint.open(path, _run_identity(), total_cells=400)

    with pytest.raises(RuntimeError, match="CHECKPOINT_CELL_ORDER_INVALID"):
        checkpoint.record_cell(1, "f" * 64)


def test_performance_metrics_and_basic_gate_are_fail_closed() -> None:
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


def test_sequential_cells_resume_from_atomic_checkpoint(tmp_path: Path) -> None:
    specs = (
        Specification("residual_momentum", 5, 5, 1),
        Specification("trend_quality", 5, 5, 1),
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
