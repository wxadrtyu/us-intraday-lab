"""Evaluate the frozen asymmetric champion on untouched 2026-Q1 sessions."""

from __future__ import annotations

import json
import math
from pathlib import Path

from us_intraday_lab.backtest.costs import COST_SCENARIOS
from us_intraday_lab.contracts.backtests import BacktestJob, CostModelIds
from us_intraday_lab.contracts.strategies import StrategyDefinition
from us_intraday_lab.long_horizon.engine import (
    FIVE_MINUTE_ENGINE_ID,
    FiveMinuteBacktestEngine,
    _feature_frame,
    _normalize_bars,
    five_minute_input_sha256,
)
from us_intraday_lab.long_horizon.hf_snapshot import HfFiveMinuteSnapshotStore
from us_intraday_lab.long_horizon.metrics import compute_long_horizon_oos_metrics
from us_intraday_lab.long_horizon.orchestrator import (
    _session_returns,
    cost_adjusted_trade_session_returns,
)
from us_intraday_lab.strategy.compiler import compile_strategy

ROOT = Path(r"G:\us-intraday-lab")
DATASET_ID = "hf-finnhub-5min-50ac3b84b79898a4e0d4ee63cc4947dc"
SELECTION = (
    ROOT
    / "artifacts"
    / "long_horizon"
    / "experiments"
    / ("lh-aa3bbf0521e40570ee4ae707fdf1ee84")
    / "selection-a072c8b375e2cd0ac1a53e1cd7d515de3be9d57d0bbaea682ccc571a445df617.json"
)


def main() -> None:
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    winner_id = str(selection["winner_id"])
    strategy = StrategyDefinition.model_validate(
        next(item for item in selection["survivor_strategies"] if item["strategy_id"] == winner_id)
    )
    store = HfFiveMinuteSnapshotStore(root=ROOT, dataset_id=DATASET_ID)
    all_sessions = store.accepted_sessions
    forward_sessions = tuple(session for session in all_sessions if session.year == 2026)
    warmup_sessions = tuple(session for session in all_sessions if session.year == 2025)
    if len(forward_sessions) != 60 or not warmup_sessions:
        raise ValueError("forward dataset must contain 60 frozen 2026 sessions plus warmup")
    bars = store.read_sessions(all_sessions)
    compiled = compile_strategy(strategy)
    job = BacktestJob.create(
        schema_version="1.0.0",
        strategy_id=compiled.definition_fingerprint,
        dataset_id=DATASET_ID,
        engine_id=FIVE_MINUTE_ENGINE_ID,
        calendar_id="XNYS@frozen-forward-2026q1-v1",
        input_data_sha256=five_minute_input_sha256(bars),
        initial_cash=100_000.0,
        closeout_buffer_minutes=5,
        cost_model_ids=CostModelIds(
            **{
                scenario: COST_SCENARIOS[scenario].model_id
                for scenario in ("optimistic", "base", "stress")
            }
        ),
    )
    engine = FiveMinuteBacktestEngine(job=job, strategy=compiled)
    features = _feature_frame(_normalize_bars(bars, symbols=strategy.symbols))
    forward_frame = features.loc[features["session_date"].isin(forward_sessions)].copy()
    base = engine._run_scenario(forward_frame, scenario="base")
    stress = engine._run_scenario(forward_frame, scenario="stress")
    base_returns = _session_returns(base.equity_curve, initial_cash=base.initial_cash)
    cost_returns = cost_adjusted_trade_session_returns(
        base.trades,
        forward_sessions,
        initial_cash=base.initial_cash,
        cost_multiplier=1.5,
    )
    benchmark_bars = bars.loc[
        bars["session_date"].isin(forward_sessions) & (bars["symbol"] == "TQQQ")
    ].sort_values(["session_date", "timestamp"], kind="stable")
    closes = benchmark_bars.groupby("session_date", sort=True, observed=True)["close"].last()
    benchmark = tuple(float(value) for value in closes.pct_change().fillna(0.0))
    metrics = compute_long_horizon_oos_metrics(
        strategy_session_returns=base_returns,
        benchmark_session_returns=benchmark,
        cost_1_5x_session_returns=cost_returns,
    )
    pnl_by_symbol = {
        symbol: math.fsum(trade.net_pnl for trade in base.trades if trade.symbol == symbol)
        for symbol in strategy.symbols
    }
    print(
        json.dumps(
            {
                "base_max_drawdown": base.metrics["max_drawdown"],
                "base_profit_factor": base.metrics["profit_factor"],
                "closed_trades": len(base.trades),
                "cost_1_5x_annualized_return": metrics.cost_1_5x_annualized_return,
                "cost_1_5x_total_return": metrics.cost_1_5x_total_return,
                "dataset_id": DATASET_ID,
                "forward_end": forward_sessions[-1].isoformat(),
                "forward_sessions": len(forward_sessions),
                "forward_start": forward_sessions[0].isoformat(),
                "information_ratio": metrics.information_ratio,
                "pnl_by_symbol": pnl_by_symbol,
                "strategy_total_return": metrics.strategy_total_return,
                "stress_total_return": math.prod(
                    1.0 + value
                    for value in _session_returns(
                        stress.equity_curve, initial_cash=stress.initial_cash
                    )
                )
                - 1.0,
                "warmup_sessions": len(warmup_sessions),
                "winner_id": winner_id,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
