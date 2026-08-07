"""Compare causal trade additions from a small ensemble-threshold relaxation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from us_intraday_lab.backtest.costs import COST_SCENARIOS
from us_intraday_lab.backtest.engine import (
    CALENDAR_ID,
    ENGINE_ID,
    BacktestEngine,
    input_data_sha256,
)
from us_intraday_lab.contracts.backtests import BacktestJob, CostModelIds
from us_intraday_lab.contracts.strategies import StrategyDefinition
from us_intraday_lab.data.catalog import connect_catalog
from us_intraday_lab.strategy.compiler import compile_strategy
from us_intraday_lab.strategy.features import compute_feature_frame
from us_intraday_lab.validation.splits import create_chronological_split

ROOT = Path(__file__).resolve().parents[1]


def definition(
    secondary_return_max: float,
    *,
    bridge: bool = False,
    bridge_return_max: float = -0.0018,
    bridge_return_3_max: float = 0.0,
) -> StrategyDefinition:
    branches: list[dict[str, object]] = [
        {
            "all": [
                {"indicator": "vwap_distance_bps", "op": "lt", "value": -10},
                {"indicator": "return_1", "op": "lt", "value": -0.00075},
                {"indicator": "range_position", "op": "lt", "value": 0.6},
                {"indicator": "minutes_from_open", "op": "gt", "value": 180},
            ]
        },
        {
            "all": [
                {"indicator": "ema_spread", "op": "gt", "value": 0},
                {"indicator": "return_1", "op": "lt", "value": secondary_return_max},
                {"indicator": "range_position", "op": "lt", "value": 0.3},
                {"indicator": "minutes_from_open", "op": "gt", "value": 120},
            ]
        },
    ]
    if bridge:
        branches.append(
            {
                "all": [
                    {"indicator": "ema_spread", "op": "gt", "value": 0},
                    {"indicator": "return_1", "op": "lt", "value": bridge_return_max},
                    {"indicator": "return_3", "op": "lte", "value": bridge_return_3_max},
                ]
            }
        )
    return StrategyDefinition.model_validate(
        {
            "strategy_id": f"ensemble-diagnostic-{secondary_return_max}",
            "dsl_version": "1.0.0",
            "symbols": ["SPY", "QQQ", "IWM"],
            "signal_bar_size": "15min",
            "entry": {"any": branches},
            "exit": {"indicator": "minutes_from_open", "op": "gte", "value": 390},
            "risk": {
                "stop_loss_bps": 10000,
                "take_profit_bps": 10000,
                "max_holding_minutes": 105,
                "cooldown_minutes": 15,
                "max_entries_per_session": 3,
                "sizing_preset": "equal_cash_conservative",
            },
            "order_type": "market",
        }
    )


def load_frames(sessions: tuple[date, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    placeholders = ", ".join("?" for _ in sessions)
    with connect_catalog(root=ROOT) as connection:
        minute = connection.execute(
            f"SELECT * FROM bars_1m WHERE session_date IN ({placeholders}) "
            "AND symbol IN ('SPY', 'QQQ', 'IWM') ORDER BY session_date, timestamp, symbol",
            list(sessions),
        ).df()
        signal = connection.execute(
            f"SELECT * FROM bars_15m WHERE session_date IN ({placeholders}) "
            "AND symbol IN ('SPY', 'QQQ', 'IWM') ORDER BY session_date, available_at, symbol",
            list(sessions),
        ).df()
    minute["session_date"] = minute["session_date"].map(
        lambda value: value.date() if isinstance(value, pd.Timestamp) else value
    )
    signal["session_date"] = signal["session_date"].map(
        lambda value: value.date() if isinstance(value, pd.Timestamp) else value
    )
    minute["timestamp"] = pd.to_datetime(minute["timestamp"], utc=True)
    signal["available_at"] = pd.to_datetime(signal["available_at"], utc=True)
    return minute, signal


def run(defn: StrategyDefinition, minute: pd.DataFrame, signal: pd.DataFrame):
    compiled = compile_strategy(defn)
    job = BacktestJob.create(
        schema_version="1.0.0",
        strategy_id=compiled.definition_fingerprint,
        dataset_id="ensemble-causal-diagnostic",
        engine_id=ENGINE_ID,
        calendar_id=CALENDAR_ID,
        input_data_sha256=input_data_sha256(minute, signal),
        initial_cash=100_000.0,
        closeout_buffer_minutes=5,
        cost_model_ids=CostModelIds(
            optimistic=COST_SCENARIOS["optimistic"].model_id,
            base=COST_SCENARIOS["base"].model_id,
            stress=COST_SCENARIOS["stress"].model_id,
        ),
    )
    return BacktestEngine(job=job, strategy=compiled).run_scenario(
        minute_bars=minute,
        signal_bars=signal,
        cost_scenario="base",
    )


def trade_key(trade) -> tuple[str, date, pd.Timestamp]:
    return trade.symbol, trade.session, pd.Timestamp(trade.entry_time)


def causal_row(trade, features: pd.DataFrame) -> dict[str, object]:
    available = pd.to_datetime(features["available_at"], utc=True)
    eligible = features.loc[
        (features["symbol"] == trade.symbol)
        & (features["session_date"] == trade.session)
        & (available < pd.Timestamp(trade.entry_time))
    ].sort_values("available_at")
    row = eligible.iloc[-1]
    names = (
        "return_1",
        "return_3",
        "ema_spread",
        "rsi",
        "atr_bps",
        "volume_ratio",
        "vwap_distance_bps",
        "range_position",
        "minutes_from_open",
    )
    return {
        "symbol": trade.symbol,
        "session": trade.session.isoformat(),
        "entry_time": trade.entry_time.isoformat(),
        "net_pnl": trade.net_pnl,
        **{name: float(row[name]) for name in names},
    }


def main() -> None:
    with connect_catalog(root=ROOT) as connection:
        sessions = tuple(
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT session_date FROM bars_15m "
                "WHERE symbol IN ('SPY', 'QQQ', 'IWM') AND session_date >= DATE '2026-04-13' "
                "ORDER BY session_date"
            ).fetchall()
        )
    split = create_chronological_split(sessions, split_id="ensemble-causal-diagnostic")
    for phase, phase_sessions in (
        ("train", split.train_sessions),
        ("validation", split.validation_sessions),
        ("final_test", split.final_test_sessions),
    ):
        minute, signal = load_frames(phase_sessions)
        features = compute_feature_frame(signal)
        strict = run(definition(-0.002), minute, signal)
        relaxed = run(definition(-0.002, bridge=True), minute, signal)
        strict_keys = {trade_key(trade) for trade in strict.trades}
        relaxed_keys = {trade_key(trade) for trade in relaxed.trades}
        print(
            f"\n{phase}: strict={len(strict.trades)} relaxed={len(relaxed.trades)} "
            f"strict_return={strict.metrics['net_return']:.8f} "
            f"relaxed_return={relaxed.metrics['net_return']:.8f} "
            f"strict_pf={strict.metrics['profit_factor']:.4f} "
            f"relaxed_pf={relaxed.metrics['profit_factor']:.4f}"
        )
        print("added")
        for trade in relaxed.trades:
            if trade_key(trade) not in strict_keys:
                print(causal_row(trade, features))
        print("removed")
        for trade in strict.trades:
            if trade_key(trade) not in relaxed_keys:
                print(causal_row(trade, features))


if __name__ == "__main__":
    main()
