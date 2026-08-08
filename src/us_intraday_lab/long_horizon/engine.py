"""Conservative event-driven execution for the closed five-minute research lane."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import floor, isfinite
from types import MappingProxyType
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

from us_intraday_lab.backtest.costs import COST_SCENARIOS
from us_intraday_lab.backtest.engine import (
    BacktestEvent,
    EngineRun,
    JsonScalar,
    ScenarioRun,
    run_id_for_job,
)
from us_intraday_lab.backtest.metrics import EquityPoint, TradeRecord
from us_intraday_lab.backtest.portfolio import Position
from us_intraday_lab.contracts.backtests import BacktestJob, CostScenario
from us_intraday_lab.contracts.orders import OrderIntent, OrderReasonCode
from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.strategy.compiler import compile_strategy
from us_intraday_lab.strategy.operators import (
    AllOperator,
    AnyOperator,
    ComparisonOperator,
    CompiledStrategy,
    FeatureRow,
    RuleOperator,
)

FIVE_MINUTE_ENGINE_ID = "five-minute-engine-1.0.0"
FIVE_MINUTE_FEATURE_SET_VERSION = "5m-v1.0.0"
_SCENARIOS: tuple[CostScenario, ...] = ("optimistic", "base", "stress")
_REQUIRED = frozenset(
    {
        "symbol",
        "timestamp",
        "available_at",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "session_date",
    }
)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc(value: object, *, name: str) -> datetime:
    timestamp = pd.Timestamp(cast(str | int | float | date | datetime, value))
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return timestamp.tz_convert("UTC").to_pydatetime()


def _session_date(value: object) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError("session_date must contain exact date values")
    return value


def five_minute_input_sha256(bars_5m: pd.DataFrame) -> str:
    """Hash every normalized field that can affect five-minute execution."""

    missing = sorted(_REQUIRED.difference(bars_5m.columns))
    if missing:
        raise ValueError("five-minute bars lack required columns: " + ",".join(missing))
    rows: list[dict[str, object]] = []
    for raw in bars_5m.loc[:, sorted(_REQUIRED)].to_dict(orient="records"):
        row: dict[str, object] = {
            "available_at": _iso(_utc(raw["available_at"], name="available_at")),
            "session_date": _session_date(raw["session_date"]).isoformat(),
            "symbol": str(raw["symbol"]),
            "timestamp": _iso(_utc(raw["timestamp"], name="timestamp")),
        }
        for field in ("open", "high", "low", "close", "volume"):
            value = float(cast(Any, raw[field]))
            if not isfinite(value):
                raise ValueError(f"{field} must be finite")
            row[field] = value
        rows.append(row)
    rows.sort(
        key=lambda row: (
            cast(str, row["session_date"]),
            cast(str, row["available_at"]),
            cast(str, row["symbol"]),
        )
    )
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _normalize_bars(
    bars: pd.DataFrame,
    *,
    symbols: tuple[str, ...] = ("AAPL", "QQQ"),
) -> pd.DataFrame:
    missing = sorted(_REQUIRED.difference(bars.columns))
    if missing:
        raise ValueError("five-minute bars lack required columns: " + ",".join(missing))
    frame = bars.loc[:, sorted(_REQUIRED)].copy()
    if tuple(sorted(set(frame["symbol"]))) != tuple(sorted(symbols)):
        raise ValueError("five-minute engine input must exactly cover strategy symbols")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True)
    if frame.duplicated(["symbol", "session_date", "available_at"]).any():
        raise ValueError("five-minute bars must be unique by symbol/session/available_at")
    for field in ("open", "high", "low", "close", "volume"):
        frame[field] = pd.to_numeric(frame[field], errors="raise").astype("float64")
        if not np.isfinite(frame[field]).all():
            raise ValueError(f"{field} must be finite")
    invalid = (
        (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
        | (frame["volume"] < 0)
    )
    if invalid.any():
        raise ValueError("five-minute bars contain invalid OHLCV")
    return frame.sort_values(
        ["session_date", "available_at", "symbol"], kind="stable", ignore_index=True
    )


def _feature_frame(bars: pd.DataFrame) -> pd.DataFrame:
    computed: list[pd.DataFrame] = []
    for (_symbol, raw_session), raw_group in bars.groupby(
        ["symbol", "session_date"], sort=True, observed=True
    ):
        session = _session_date(raw_session)
        group = raw_group.sort_values("available_at", kind="stable").copy()
        close = group["close"]
        high = group["high"]
        low = group["low"]
        volume = group["volume"]
        group["return_1"] = close.pct_change(fill_method=None)
        group["return_3"] = close.pct_change(3, fill_method=None)
        fast = close.ewm(span=3, adjust=False, min_periods=3).mean()
        slow = close.ewm(span=8, adjust=False, min_periods=8).mean()
        group["ema_spread"] = fast / slow - 1.0
        change = close.diff()
        gain = change.clip(lower=0).rolling(14, min_periods=14).mean()
        loss = (-change.clip(upper=0)).rolling(14, min_periods=14).mean()
        strength = gain / loss.replace(0.0, np.nan)
        rsi = 100.0 - 100.0 / (1.0 + strength)
        group["rsi"] = rsi.mask((gain == 0) & (loss == 0), 50.0).mask(
            (gain > 0) & (loss == 0), 100.0
        )
        previous = close.shift(1)
        true_range = pd.concat(
            [high - low, (high - previous).abs(), (low - previous).abs()], axis=1
        ).max(axis=1)
        group["atr_bps"] = true_range.rolling(14, min_periods=14).mean() / close * 10_000
        mean_volume = volume.rolling(20, min_periods=20).mean().replace(0.0, np.nan)
        group["volume_ratio"] = volume / mean_volume
        typical = (high + low + close) / 3.0
        cumulative_volume = volume.cumsum().replace(0.0, np.nan)
        vwap = (typical * volume).cumsum() / cumulative_volume
        group["vwap_distance_bps"] = (close / vwap - 1.0) * 10_000
        width = high - low
        group["range_position"] = ((close - low) / width.replace(0.0, np.nan)).mask(
            (width == 0) & (close == high) & (close == low), 0.5
        )
        session_open = expected_minute_index(session)[0]
        group["minutes_from_open"] = (
            (group["available_at"] - session_open).dt.total_seconds() / 60.0
        )
        group["feature_set_version"] = FIVE_MINUTE_FEATURE_SET_VERSION
        computed.append(group)
    return pd.concat(computed, ignore_index=True).sort_values(
        ["session_date", "available_at", "symbol"], kind="stable", ignore_index=True
    )


def _matches(rule: RuleOperator, features: FeatureRow) -> bool:
    if type(rule) is ComparisonOperator:
        value = rule.indicator_fn(features)
        return (
            value is not None
            and not pd.isna(value)
            and isfinite(float(value))
            and rule.comparison_fn(float(value), rule.threshold)
        )
    if type(rule) is AllOperator:
        return all(_matches(child, features) for child in rule.children)
    if type(rule) is AnyOperator:
        return any(_matches(child, features) for child in rule.children)
    raise TypeError("unsupported compiled rule")


def _observable(rule: RuleOperator, features: FeatureRow) -> bool:
    if type(rule) is ComparisonOperator:
        value = rule.indicator_fn(features)
        return value is not None and not pd.isna(value) and isfinite(float(value))
    if type(rule) is AllOperator:
        return all(_observable(child, features) for child in rule.children)
    if type(rule) is AnyOperator:
        return all(_observable(child, features) for child in rule.children)
    raise TypeError("unsupported compiled rule")


@dataclass(slots=True)
class _OpenTrade:
    symbol: str
    session: date
    quantity: int
    entry_time: datetime
    entry_price: float
    entry_cost: float
    entry_index: int


@dataclass(slots=True)
class _Pending:
    intent: OrderIntent
    signal_reference: float
    forced: bool = False


class FiveMinuteBacktestEngine:
    """Evaluate completed 5m features and fill no earlier than the following bar."""

    def __init__(self, *, job: BacktestJob, strategy: CompiledStrategy) -> None:
        if type(job) is not BacktestJob or type(strategy) is not CompiledStrategy:
            raise TypeError("job and strategy must be exact contract instances")
        if strategy.definition.signal_bar_size != "5min":
            raise ValueError("five-minute engine requires a 5min strategy")
        if strategy != compile_strategy(strategy.definition):
            raise ValueError("compiled strategy content does not match its definition")
        if job.engine_id != FIVE_MINUTE_ENGINE_ID:
            raise ValueError("unsupported five-minute engine identity")
        if job.strategy_id != strategy.definition_fingerprint:
            raise ValueError("job strategy identity mismatch")
        expected_costs = {scenario: COST_SCENARIOS[scenario].model_id for scenario in _SCENARIOS}
        if job.cost_model_ids.model_dump() != expected_costs:
            raise ValueError("job cost identities do not match configured scenarios")
        self.job = job
        self.strategy = strategy
        self.run_id = run_id_for_job(job)

    def run(self, *, bars_5m: pd.DataFrame) -> EngineRun:
        if five_minute_input_sha256(bars_5m) != self.job.input_data_sha256:
            raise ValueError("five-minute input does not match BacktestJob identity")
        frame = _feature_frame(_normalize_bars(bars_5m, symbols=self.strategy.symbols))
        scenarios = {
            scenario: self._run_scenario(frame, scenario=scenario) for scenario in _SCENARIOS
        }
        return EngineRun(
            job=self.job,
            run_id=self.run_id,
            scenarios=MappingProxyType(scenarios),
        )

    def _intent(
        self,
        *,
        symbol: str,
        session: date,
        side: Literal["buy", "sell"],
        quantity: int,
        signal_time: datetime,
        reason: OrderReasonCode,
        reference_price: float,
        scenario: CostScenario,
        forced: bool = False,
    ) -> OrderIntent:
        order_type = "market" if forced else self.strategy.order_type
        limit_price = None
        if order_type == "limit":
            direction = 1.0 if side == "buy" else -1.0
            limit_price = reference_price * (
                1.0 + direction * COST_SCENARIOS[scenario].price_impact_bps / 10_000
            )
        identity = {
            "reason": reason,
            "run_id": self.run_id,
            "scenario": scenario,
            "session": session.isoformat(),
            "side": side,
            "signal_time": _iso(signal_time),
            "symbol": symbol,
        }
        order_id = "order-" + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return OrderIntent(
            schema_version="1.0.0",
            run_id=self.run_id,
            strategy_id=self.strategy.strategy_id,
            symbol=symbol,
            session=session,
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            signal_time=signal_time,
            eligible_time=signal_time + timedelta(minutes=5),
            reason_code=reason,
            idempotency_key=order_id,
        )

    def _run_scenario(
        self,
        frame: pd.DataFrame,
        *,
        scenario: CostScenario,
    ) -> ScenarioRun:
        cost_model = COST_SCENARIOS[scenario]
        cash = self.job.initial_cash
        positions: dict[str, _OpenTrade] = {}
        pending: dict[str, _Pending] = {}
        cooldown_until: dict[str, datetime] = {}
        entries_by_session: dict[date, int] = {}
        trades: list[TradeRecord] = []
        intents: list[OrderIntent] = []
        events: list[BacktestEvent] = []
        equity: list[EquityPoint] = []

        def emit(
            event_type: Any,
            event_time: datetime,
            session: date,
            symbol: str | None = None,
            **details: JsonScalar,
        ) -> None:
            events.append(
                BacktestEvent(
                    sequence=len(events) + 1,
                    event_type=event_type,
                    event_time=event_time,
                    scenario=scenario,
                    session=session,
                    symbol=symbol,
                    details=MappingProxyType(dict(sorted(details.items()))),
                )
            )

        def close_trade(
            position: _OpenTrade,
            *,
            exit_time: datetime,
            exit_price: float,
            forced: bool,
        ) -> None:
            nonlocal cash
            exit_cost = cost_model.variable_cost(exit_price * position.quantity, position.quantity)
            gross = (exit_price - position.entry_price) * position.quantity
            total_cost = position.entry_cost + exit_cost
            cash += exit_price * position.quantity - exit_cost
            trades.append(
                TradeRecord(
                    symbol=position.symbol,
                    session=position.session,
                    quantity=position.quantity,
                    entry_time=position.entry_time,
                    exit_time=exit_time,
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    gross_pnl=gross,
                    net_pnl=gross - total_cost,
                    cost_paid=total_cost,
                    forced=forced,
                )
            )
            positions.pop(position.symbol)
            cooldown_until[position.symbol] = exit_time + timedelta(
                minutes=self.strategy.risk.cooldown_minutes
            )
            emit("POSITION_CLOSED", exit_time, position.session, position.symbol, forced=forced)

        for raw_session, session_frame in frame.groupby("session_date", sort=True, observed=True):
            session = _session_date(raw_session)
            entries_by_session[session] = 0
            times = tuple(sorted(session_frame["available_at"].unique()))
            last_rows: dict[str, pd.Series[Any]] = {}
            for bar_index, raw_time in enumerate(times):
                event_time = _utc(raw_time, name="available_at")
                rows = session_frame.loc[session_frame["available_at"] == raw_time].sort_values(
                    "symbol", kind="stable"
                )
                for _, row in rows.iterrows():
                    symbol = str(row["symbol"])
                    last_rows[symbol] = row
                    emit("BAR_CLOSED_5M", event_time, session, symbol)
                    working = pending.pop(symbol, None)
                    if working is not None and working.intent.eligible_time <= event_time:
                        intent = working.intent
                        raw_open = float(row["open"])
                        crossed = (
                            intent.order_type == "market"
                            or (
                                intent.side == "buy"
                                and intent.limit_price is not None
                                and float(row["low"]) <= intent.limit_price
                            )
                            or (
                                intent.side == "sell"
                                and intent.limit_price is not None
                                and float(row["high"]) >= intent.limit_price
                            )
                        )
                        if crossed:
                            fill_price = (
                                raw_open
                                if intent.order_type == "market"
                                else cast(float, intent.limit_price)
                            )
                            if intent.side == "buy" and symbol not in positions:
                                entry_cost = cost_model.variable_cost(
                                    fill_price * intent.quantity, intent.quantity
                                )
                                required_cash = fill_price * intent.quantity + entry_cost
                                if required_cash <= cash:
                                    cash -= required_cash
                                    positions[symbol] = _OpenTrade(
                                        symbol=symbol,
                                        session=session,
                                        quantity=intent.quantity,
                                        entry_time=event_time,
                                        entry_price=fill_price,
                                        entry_cost=entry_cost,
                                        entry_index=bar_index,
                                    )
                                    entries_by_session[session] += 1
                                    emit("POSITION_OPENED", event_time, session, symbol)
                            elif intent.side == "sell" and symbol in positions:
                                close_trade(
                                    positions[symbol],
                                    exit_time=event_time,
                                    exit_price=fill_price,
                                    forced=working.forced,
                                )

                    position = positions.get(symbol)
                    if position is not None and bar_index > position.entry_index:
                        stop = position.entry_price * (
                            1.0 - self.strategy.risk.stop_loss_bps / 10_000
                        )
                        target = position.entry_price * (
                            1.0 + self.strategy.risk.take_profit_bps / 10_000
                        )
                        if float(row["low"]) <= stop:
                            close_trade(
                                position,
                                exit_time=event_time,
                                exit_price=stop,
                                forced=False,
                            )
                            position = None
                        elif float(row["high"]) >= target:
                            close_trade(
                                position,
                                exit_time=event_time,
                                exit_price=target,
                                forced=False,
                            )
                            position = None

                    features = cast(FeatureRow, row.to_dict())
                    if _observable(self.strategy.entry, features):
                        emit("ENTRY_CANDIDATE", event_time, session, symbol)
                    entry_matches = _matches(self.strategy.entry, features)
                    if entry_matches:
                        emit("ENTRY_OPPORTUNITY", event_time, session, symbol)
                    if symbol not in pending and position is None:
                        cooldown = cooldown_until.get(symbol)
                        if (
                            (cooldown is None or event_time >= cooldown)
                            and entries_by_session[session]
                            < self.strategy.risk.max_entries_per_session
                            and entry_matches
                            and bar_index + 1 < len(times)
                        ):
                            reference = float(row["close"])
                            quantity = floor(cash * 0.49 / reference)
                            if self.strategy.risk.sizing_preset == "equal_risk_conservative":
                                risk_per_share = reference * self.strategy.risk.stop_loss_bps / 10_000
                                quantity = min(
                                    quantity,
                                    floor((cash * 0.005) / max(risk_per_share, 1e-12)),
                                )
                            if quantity > 0:
                                intent = self._intent(
                                    symbol=symbol,
                                    session=session,
                                    side="buy",
                                    quantity=quantity,
                                    signal_time=event_time,
                                    reason="entry_signal",
                                    reference_price=reference,
                                    scenario=scenario,
                                )
                                intents.append(intent)
                                pending[symbol] = _Pending(intent, reference)
                                emit("ORDER_INTENT_CREATED", event_time, session, symbol)
                    elif position is not None and symbol not in pending:
                        holding_due = event_time >= position.entry_time + timedelta(
                            minutes=self.strategy.risk.max_holding_minutes
                        )
                        if (_matches(self.strategy.exit, features) or holding_due) and bar_index + 1 < len(times):
                            reason: OrderReasonCode = "max_holding" if holding_due else "exit_signal"
                            intent = self._intent(
                                symbol=symbol,
                                session=session,
                                side="sell",
                                quantity=position.quantity,
                                signal_time=event_time,
                                reason=reason,
                                reference_price=float(row["close"]),
                                scenario=scenario,
                            )
                            intents.append(intent)
                            pending[symbol] = _Pending(intent, float(row["close"]))
                            emit("ORDER_INTENT_CREATED", event_time, session, symbol)

                marked = cash + sum(
                    position.quantity
                    * float(last_rows[position.symbol]["close"])
                    for position in positions.values()
                )
                gross = sum(
                    position.quantity
                    * float(last_rows[position.symbol]["close"])
                    for position in positions.values()
                )
                equity.append(
                    EquityPoint(
                        event_time=event_time,
                        session=session,
                        equity=marked,
                        gross_exposure=gross,
                    )
                )
            pending.clear()
            if times:
                close_time = _utc(times[-1], name="available_at")
                for symbol in tuple(sorted(positions)):
                    position = positions[symbol]
                    if position.session == session:
                        close_trade(
                            position,
                            exit_time=close_time,
                            exit_price=float(last_rows[symbol]["close"]),
                            forced=True,
                        )
                if equity:
                    equity[-1] = EquityPoint(
                        event_time=close_time,
                        session=session,
                        equity=cash,
                        gross_exposure=0.0,
                    )
                emit("SESSION_FINALIZED", close_time, session)

        return ScenarioRun(
            cost_scenario=scenario,
            events=tuple(events),
            intents=tuple(intents),
            trades=tuple(trades),
            equity_curve=tuple(equity),
            initial_cash=self.job.initial_cash,
            final_cash=cash,
            final_positions=tuple(
                Position(
                    symbol=position.symbol,
                    quantity=position.quantity,
                    average_cost=position.entry_price,
                    market_price=position.entry_price,
                )
                for position in positions.values()
            ),
        )
