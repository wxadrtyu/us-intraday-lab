"""Alpaca IEX history and pure v4 research-shadow session evaluation."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo

import pandas as pd

from us_intraday_lab.dual_sleeve import DualSleeveParameters

PAPER_KEY_VARIABLE = "ALPACA_PAPER_API_KEY"
PAPER_SECRET_VARIABLE = "ALPACA_PAPER_SECRET_KEY"
NEW_YORK = ZoneInfo("America/New_York")


class _HistoricalClient(Protocol):
    def get_stock_bars(self, request: object) -> Any: ...


HistoricalClientFactory = Callable[[str, str], _HistoricalClient]


def _client_factory(api_key: str, secret_key: str) -> _HistoricalClient:
    from alpaca.data.historical import StockHistoricalDataClient

    return cast(
        _HistoricalClient,
        StockHistoricalDataClient(api_key=api_key, secret_key=secret_key),
    )


class AlpacaIexHistory:
    """Read-only Alpaca IEX history adapter; it has no trading-client dependency."""

    def __init__(self, client: _HistoricalClient) -> None:
        self._client = client

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        client_factory: HistoricalClientFactory = _client_factory,
    ) -> AlpacaIexHistory:
        values = os.environ if environ is None else environ
        api_key = values.get(PAPER_KEY_VARIABLE, "")
        secret_key = values.get(PAPER_SECRET_VARIABLE, "")
        if not api_key or not secret_key:
            raise RuntimeError("RESEARCH_SHADOW_MARKET_DATA_CREDENTIAL_MISSING")
        return cls(client_factory(api_key, secret_key))

    def fetch(
        self,
        *,
        symbols: tuple[str, ...],
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        if not symbols or len(symbols) != len(set(symbols)):
            raise ValueError("research shadow symbols must be non-empty and unique")
        if start.utcoffset() is None or end.utcoffset() is None or start >= end:
            raise ValueError("research shadow history bounds are invalid")
        request = StockBarsRequest(
            symbol_or_symbols=list(symbols),
            timeframe=TimeFrame.Minute,
            start=start.astimezone(UTC),
            end=end.astimezone(UTC),
            adjustment=Adjustment.ALL,
            feed=DataFeed.IEX,
        )
        response = self._client.get_stock_bars(request)
        frame = response.df.reset_index()
        required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
        if not required.issubset(frame.columns):
            raise RuntimeError("ALPACA_IEX_HISTORY_SCHEMA_MISMATCH")
        retained = frame.loc[:, sorted(required)].copy()
        retained["timestamp"] = pd.to_datetime(retained["timestamp"], utc=True)
        retained["symbol"] = retained["symbol"].astype(str)
        return cast(
            pd.DataFrame,
            retained.sort_values(["timestamp", "symbol"]).reset_index(drop=True),
        )


@dataclass(frozen=True, slots=True)
class DualSleeveShadowObservation:
    session_date: date
    stock_signal: bool
    stock_symbol: str | None
    spy_signal: bool
    stock_sleeve_return: float
    spy_sleeve_return: float
    strategy_return: float
    benchmark_return: float
    target_spy_minutes: int
    target_minimum_stock_minutes: int
    context_sessions: int

    def as_record(
        self,
        parameters: DualSleeveParameters,
        *,
        provider: str = "alpaca",
        feed: str = "iex",
    ) -> dict[str, object]:
        if not provider or not feed:
            raise ValueError("research shadow provider metadata cannot be empty")
        return {
            "schema_version": "1.0.0",
            "provider": provider,
            "feed": feed,
            "session_date": self.session_date.isoformat(),
            "parameters": {
                "stock_excess_floor": parameters.stock_excess_floor,
                "stock_range_floor": parameters.stock_range_floor,
                "spy_current_floor": parameters.spy_current_floor,
                "spy_exit_minute": parameters.spy_exit_minute,
            },
            "signals": {
                "stock": self.stock_signal,
                "stock_symbol": self.stock_symbol,
                "spy": self.spy_signal,
            },
            "theoretical": {
                "stock_sleeve_return": self.stock_sleeve_return,
                "spy_sleeve_return": self.spy_sleeve_return,
                "strategy_return": self.strategy_return,
                "benchmark_return": self.benchmark_return,
            },
            "quality": {
                "target_spy_minutes": self.target_spy_minutes,
                "target_minimum_stock_minutes": self.target_minimum_stock_minutes,
                "context_sessions": self.context_sessions,
            },
        }


def _minute_index(timestamp: pd.Series) -> pd.Series:
    localized = timestamp.dt.tz_convert(NEW_YORK)
    return cast(pd.Series, (localized.dt.hour - 9) * 60 + localized.dt.minute - 30)


def _at(frame: pd.DataFrame, minute: int, column: str) -> float:
    values = frame.loc[frame["minute_index"] == minute, column]
    if len(values) != 1:
        raise ValueError(f"target session is missing exact minute {minute}")
    return float(values.iloc[0])


def evaluate_alpaca_dual_sleeve_session(
    bars: pd.DataFrame,
    *,
    session_date: date,
    universe: tuple[str, ...],
    parameters: DualSleeveParameters,
    round_trip_cost: float,
) -> DualSleeveShadowObservation:
    """Evaluate one completed IEX session with causal v4 semantics and prior context."""

    required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(bars.columns):
        raise ValueError("research shadow bars have an invalid schema")
    if tuple(sorted(set(universe))) != universe or len(universe) not in {50, 51}:
        raise ValueError("research shadow universe must contain 50 or 51 sorted symbols")
    if not 0.0 <= round_trip_cost < 0.01:
        raise ValueError("research shadow round-trip cost is invalid")
    frame = bars.loc[:, list(required)].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    localized = frame["timestamp"].dt.tz_convert(NEW_YORK)
    frame["session_date"] = localized.dt.date
    frame["minute_index"] = _minute_index(frame["timestamp"])
    frame = frame.loc[frame["minute_index"].between(0, 389)].copy()
    frame = frame.loc[frame["symbol"].isin((*universe, "SPY"))]
    if frame.duplicated(["symbol", "session_date", "minute_index"]).any():
        raise ValueError("research shadow contains duplicate IEX minutes")
    target = frame.loc[frame["session_date"] == session_date]
    spy_target = target.loc[target["symbol"] == "SPY"].sort_values("minute_index")
    spy_minutes = int(spy_target["minute_index"].nunique())
    if spy_minutes != 390:
        raise ValueError("target SPY session must contain exactly 390 IEX minutes")
    stock_counts = (
        target.loc[target["symbol"].isin(universe)].groupby("symbol")["minute_index"].nunique()
    )
    if len(stock_counts) != len(universe) or int(stock_counts.min()) < 385:
        raise ValueError("target stock session fails the frozen completeness floor")
    context_dates = tuple(
        sorted(value for value in frame["session_date"].unique() if value < session_date)
    )
    if len(context_dates) < 10:
        raise ValueError("research shadow requires at least ten prior context sessions")
    recent_dates = context_dates[-20:]

    rows = []
    for symbol in universe:
        symbol_frame = frame.loc[frame["symbol"] == symbol]
        target_symbol = symbol_frame.loc[symbol_frame["session_date"] == session_date]
        day_open = _at(target_symbol, 0, "open")
        close_45 = _at(target_symbol, 45, "close")
        opening = target_symbol.loc[target_symbol["minute_index"] <= 45]
        cumulative_volume = float(opening["volume"].sum())
        history_volume = []
        for prior_date in recent_dates:
            prior = symbol_frame.loc[
                (symbol_frame["session_date"] == prior_date) & (symbol_frame["minute_index"] <= 45)
            ]
            if len(prior):
                history_volume.append(float(prior["volume"].sum()))
        if len(history_volume) < 10:
            raise ValueError(f"insufficient relative-volume context for {symbol}")
        volume_sum = float(opening["volume"].sum())
        vwap = float((opening["close"] * opening["volume"]).sum() / volume_sum)
        rows.append(
            {
                "symbol": symbol,
                "current": close_45 / day_open - 1.0,
                "relative_volume": cumulative_volume / float(pd.Series(history_volume).median()),
                "range_position": (close_45 - float(opening["low"].min()))
                / (float(opening["high"].max()) - float(opening["low"].min())),
                "above_vwap": close_45 >= vwap,
            }
        )
    candidates = pd.DataFrame(rows).sort_values(["current", "symbol"], ascending=[False, True])
    winner = candidates.iloc[0]
    spy_open = _at(spy_target, 0, "open")
    spy_current_30 = _at(spy_target, 30, "close") / spy_open - 1.0
    spy_current_45 = _at(spy_target, 45, "close") / spy_open - 1.0
    prior_date = context_dates[-1]
    spy_prior = frame.loc[
        (frame["symbol"] == "SPY") & (frame["session_date"] == prior_date)
    ].sort_values("minute_index")
    if spy_prior["minute_index"].nunique() != 390:
        raise ValueError("prior SPY RTH session is incomplete")
    prior_spy_return = _at(spy_prior, 389, "close") / _at(spy_prior, 0, "open") - 1.0
    stock_signal = bool(
        float(winner["current"]) >= 0.003
        and float(winner["current"]) - spy_current_45 >= parameters.stock_excess_floor
        and float(winner["relative_volume"]) >= 1.5
        and bool(winner["above_vwap"])
        and float(winner["range_position"]) >= parameters.stock_range_floor
        and 0.0 <= spy_current_45 <= 0.015
    )
    spy_signal = bool(
        parameters.spy_current_floor <= spy_current_30 <= 0.04 and prior_spy_return > 0.0
    )
    stock_symbol = str(winner["symbol"]) if stock_signal else None
    stock_sleeve_return = 0.0
    stock_benchmark = 0.0
    if stock_signal and stock_symbol is not None:
        stock_target = target.loc[target["symbol"] == stock_symbol].sort_values("minute_index")
        entry = _at(stock_target, 46, "open")
        path = stock_target.loc[stock_target["minute_index"].between(46, 329)]
        hits = path.loc[path["high"] >= entry * 1.02]
        if len(hits):
            exit_minute = int(hits.iloc[0]["minute_index"])
            raw_stock_return = 0.02
            stock_benchmark = (
                _at(spy_target, exit_minute, "close") / _at(spy_target, 46, "open") - 1.0
            )
        else:
            raw_stock_return = _at(stock_target, 330, "open") / entry - 1.0
            stock_benchmark = _at(spy_target, 330, "open") / _at(spy_target, 46, "open") - 1.0
        stock_sleeve_return = 0.5 * (raw_stock_return - round_trip_cost)
        stock_benchmark *= 0.5
    spy_sleeve_return = 0.0
    spy_benchmark = 0.0
    if spy_signal:
        raw_spy_return = (
            _at(spy_target, parameters.spy_exit_minute, "open") / _at(spy_target, 31, "open") - 1.0
        )
        spy_sleeve_return = 0.5 * (raw_spy_return - round_trip_cost)
        spy_benchmark = 0.5 * raw_spy_return
    return DualSleeveShadowObservation(
        session_date=session_date,
        stock_signal=stock_signal,
        stock_symbol=stock_symbol,
        spy_signal=spy_signal,
        stock_sleeve_return=stock_sleeve_return,
        spy_sleeve_return=spy_sleeve_return,
        strategy_return=stock_sleeve_return + spy_sleeve_return,
        benchmark_return=stock_benchmark + spy_benchmark,
        target_spy_minutes=spy_minutes,
        target_minimum_stock_minutes=int(stock_counts.min()),
        context_sessions=len(context_dates),
    )


def history_bounds(session_date: date) -> tuple[datetime, datetime]:
    """Return a conservative UTC window containing twenty-plus prior XNYS sessions."""

    start = datetime.combine(session_date - timedelta(days=45), time(), NEW_YORK)
    end = datetime.combine(session_date + timedelta(days=1), time(), NEW_YORK)
    return start.astimezone(UTC), end.astimezone(UTC)
